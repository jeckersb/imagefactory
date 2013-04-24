#!/usr/bin/python
#
#   Copyright 2012 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import logging
import zope
import oz.TDL
import oz.GuestFactory
import guestfs
import libxml2
from imgfac.ApplicationConfiguration import ApplicationConfiguration
from imgfac.CloudDelegate import CloudDelegate
from imgfac.PersistentImageManager import PersistentImageManager
from imgfac.ReservationManager import ReservationManager

class IndirectionCloud(object):
    zope.interface.implements(CloudDelegate)

    def __init__(self):
        super(IndirectionCloud, self).__init__()
        self.app_config = ApplicationConfiguration().configuration
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.pim = PersistentImageManager.default_manager()
        self.res_mgr = ReservationManager()

    def builder_should_create_target_image(self, builder, target, image_id, template, parameters):
        # This plugin wants to be the only thing operating on the input image
        # We do all our work here and then return False which stops any additional activity

        # User may specify a utility image - if they do not we assume we can use the input image
        if 'utility_image' in parameters:
            utility_image_id = parameters['utility_image']
        else:
            utility_image_id = image_id


        # The utility image is what we actually re-animate with Oz
        # We borrow these variable names from code that is very similar to the Oz/TinMan OS plugin
        self.active_image = self.pim.image_with_id(utility_image_id)
        if not self.active_image:
            raise Exception("Could not find utility image with ID (%s)" % (utility_image_id) )
        self.tdlobj = oz.TDL.TDL(xmlstring=self.active_image.template)

        # We remove any packages, commands and files from the original TDL - these have already been
        # installed/executed.  We leave the repos in place, as it is possible that commands executed
        # later may depend on them
        self.tdlobj.packages = [ ]
        self.tdlobj.commands = { }
        self.tdlobj.files = { } 

        # This creates a new Oz object - replaces the auto-generated disk file location with
        # the copy of the utility image made above, and prepares an initial libvirt_xml string
        self._init_oz()
        self.guest.diskimage = utility_image_tmp
        libvirt_xml = self.guest._generate_xml("hd", None)

        # We expect to find a partial TDL document in this parameter - this is what drives the
        # tasks performed by the utility image
        if 'utility_customizations' in parameters:
            self.oz_refresh_customizations(parameters['utility_customizations'])
        else:
            self.log.info('No additional repos, packages, files or commands specified for utility tasks')

        # Make a copy of the utlity image - this will be modified and then discarded
        utility_image_tmp = self.app_config['imgdir'] + "/tmp-utility-image-" + str(builder.target_image.identifier)
        self.log.debug("Creating temporary working copy of utlity image (%s) as (%s)" % (self.active_image.data, utility_image_tmp))
        oz.ozutil.copyfile_sparse(self.active_image.data, utility_image_tmp)

        # Now we create a second disk image as working/scratch space
        # Hardcode at 30G
        # TODO: Make configurable
        # Make it, format it, copy in the base_image 
        working_space_image = self.app_config['imgdir'] + "/working-space-image-" + str(builder.target_image.identifier)
        self.create_ext2_image(working_space_image)
        # Here we finally involve the actual Base Image content - it is made available for the utlity image to modify
        self.copy_content_to_image(builder.base_image.data, working_space_image)

        input_doc = libxml2.parseDoc(libvirt_xml)
        devices = input_doc.xpathEval("/domain/devices")
        working_space = devices.newChild(None, "disk", None)
        working_space.setProp("type", "file")
        working_space.setProp("device", "disk")
        source = working_space.newChild(None, "source", None)
        source.setProp("file", working_space_image)
        target = working_space.newChild(None, "target", None)
        # TODO: Is vdb always safe?
        target.setProp("dev", "vdb")

        libvirt_xml = input_doc.serialize(None, 1)

        # Run all commands, repo injection, etc specified
        try:
            self.log.debug("Launching utility image and running any customizations specified")
            self.guest.customize(libvirt_xml)
            self.log.debug("Utility image tasks complete")
        finally:
            self.log.debug("Cleaning up install artifacts")
            self.guest.cleanup_install()

        # After shutdown, extract the
        self.copy_content_from_image("/results/images/boot.iso", working_space_image, builder.target_image.data)

        # TODO: Remove working_space image and utility_image_tmp
        return False


    def oz_refresh_customizations(self, partial_tdl):
        # This takes our already created and well formed guest object, blanks the existing
        # customizations and then attempts to add in any additional customizations found in
        # partial_tdl
        # partial_tdl need not contain the <os> section and if it does it will be ignored
        # NOTE: The files, packages and commands elements of the original TDL are already blank

        # TODO: Submit an Oz patch to make this shorter or a utility function within the TDL class

        doc = libxml2.parseDoc(partial_tdl)
        self.guest.doc = doc 

        packageslist = doc.xpathEval('/template/packages/package')
        guest._add_packages(packageslist)

        for afile in doc.xpathEval('/template/files/file'):
            name = afile.prop('name')
            if name is None:
                raise Exception("File without a name was given")
            contenttype = afile.prop('type')
            if contenttype is None:
                contenttype = 'raw'

            content = afile.getContent().strip()
            if contenttype == 'raw':
                self.files[name] = content
            elif contenttype == 'base64':
                if len(content) == 0:
                    self.guest.files[name] = ""
                else:
                    self.guest.files[name] = base64.b64decode(content)
            else:
                raise Exception("File type for %s must be 'raw' or 'base64'" % (name))

        repositorieslist = self.doc.xpathEval('/template/repositories/repository')
        guest._add_repositories(repositorieslist)

        guest.commands = self.guest._parse_commands()


    def _init_oz(self):
        # populate a config object to pass to OZ; this allows us to specify our
        # own output dir but inherit other Oz behavior
        self.oz_config = ConfigParser.SafeConfigParser()
        if self.oz_config.read("/etc/oz/oz.cfg") != []:
            self.oz_config.set('paths', 'output_dir', self.app_config["imgdir"])
            if "oz_data_dir" in self.app_config:
                self.oz_config.set('paths', 'data_dir', self.app_config["oz_data_dir"])
            if "oz_screenshot_dir" in self.app_config:
                self.oz_config.set('paths', 'screenshot_dir', self.app_config["oz_screenshot_dir"])
        else:
            raise ImageFactoryException("No Oz config file found. Can't continue.")

        # Use the factory function from Oz directly
        try:
            # Force uniqueness by overriding the name in the TDL
            self.tdlobj.name = "factory-build-" + self.active_image.identifier
            self.guest = oz.GuestFactory.guest_factory(self.tdlobj, self.oz_config, None)
            # Oz just selects a random port here - This could potentially collide if we are unlucky
            self.guest.listen_port = self.res_mgr.get_next_listen_port()
        except libvirtError, e:
            raise ImageFactoryException("Cannot connect to libvirt.  Make sure libvirt is running. [Original message: %s]" %  e.message)
        except OzException, e:
            if "Unsupported" in e.message:
                raise ImageFactoryException("TinMan plugin does not support distro (%s) update (%s) in TDL" % (self.tdlobj.distro, self.tdlobj.update) )
            else:
                raise e


    def create_ext2_image(self, image_file, image_size=(1024*1024*1024*30)):
        # Why ext2?  Why not?  There's no need for the overhead of journaling.  This disk will be mounted once and thrown away.
        self.log.debug("Creating disk image of size (%d) in file (%s) with single partition containint ext2 filesystem" % (image_size, image_file))
        raw_fs_image=open(image_file,"w")
        raw_fs_image.truncate(image_size)
        raw_fs_image.close()
        g = guestfs.GuestFS()
        g.add_drive(image_file)
        g.launch()
        g.part_disk("/dev/sda","msdos")
        g.part_set_mbr_id("/dev/sda",1,0x83)
        g.mkfs("ext2", "/dev/sda1")
        g.sync()

    def copy_content_to_image(self, filename, target_image):
        self.log.debug("Copying file (%s) into disk image (%s)" % (filename, target_image))
        g = guestfs.GuestFS()
        g.add_drive(target_image)
        g.launch()
        g.mount_options ("", "/dev/sda1", "/")
        g.upload(filename,"/input_image.raw")
        g.sync()

    def copy_content_from_image(self, filename, target_image, destination_file):
        self.log.debug("Copying file (%s) out of disk image (%s) into " % (filename, target_image))
        g = guestfs.GuestFS()
        g.add_drive(target_image)
        g.launch()
        g.mount_options ("", "/dev/sda1", "/")
        g.download(filename,destination_file)
        g.sync()

