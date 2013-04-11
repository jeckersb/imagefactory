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

        utility_image_obj = self.pim.image_with_id(utlity_image_id)

        if not utility_image_obj:
            raise Exception("Could not find utility image with ID (%s)" % (utility_image_id) )

        # Make a copy of the utlity image - this will be modified and then discarded
        utility_image_tmp = self.app_config['imgdir'] + "/tmp-utility-image-" + str(builder.target_image.identifier)
        self.log.debug("Creating temporary working copy of utlity image (%s) as (%s)" % (utility_image_obj.data, utility_image_tmp))
        oz.ozutil.copyfile_sparse(utility_image_obj.data, utility_image_tmp)

        # Launch the utility image with the input image attached read-only
        utility_tdlobj = oz.TDL.TDL(xmlstring=utility_image_obj.template)

        # populate a config object to pass to OZ; this allows us to specify our
        # own output dir but inherit other Oz behavior
        oz_config = ConfigParser.SafeConfigParser()
        if oz_config.read("/etc/oz/oz.cfg") != []:
            oz_config.set('paths', 'output_dir', self.app_config["imgdir"])
            if "oz_data_dir" in self.app_config:
                oz_config.set('paths', 'data_dir', self.app_config["oz_data_dir"])
            if "oz_screenshot_dir" in self.app_config:
                oz_config.set('paths', 'screenshot_dir', self.app_config["oz_screenshot_dir"])
        else:
            raise ImageFactoryException("No Oz config file found. Can't continue.")

        try:
            guest = oz.GuestFactory.guest_factory(utility_tdlobj, oz_config)
            # Oz just selects a random port here - This could potentially collide if we are unlucky
            guest.listen_port = self.res_mgr.get_next_listen_port()
        except:
            raise ImageFactoryException("OS plugin does not support distro (%s) update (%s) in TDL" % (self.tdlobj.distro, self.tdlobj.update) )




        # Run all commands, repo injection, etc specified

        # After shutdown, extract the

        return False

