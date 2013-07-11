# encoding: utf-8

#   Copyright 2013 Red Hat, Inc.
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

from xml.etree import ElementTree
from oz.ozutil import copyfile_sparse
import os
import tarfile
from shutil import rmtree
import uuid
import struct
import time
import glob
import tempfile
from imgfac.PersistentImageManager import PersistentImageManager

class RHEVOVFDescriptor(object):
    def __init__(self, img_uuid, vol_uuid, tpl_uuid, disk,
                 ovf_name=None, ovf_desc=None,
                 pool_id="00000000-0000-0000-0000-000000000000"):
        self.img_uuid = img_uuid
        self.vol_uuid = vol_uuid
        self.tpl_uuid = tpl_uuid
        self.disk = disk

        if ovf_name is None:
            self.ovf_name = str(self.tpl_uuid)
        else:
            self.ovf_name = ovf_name

        if ovf_desc is None:
            self.ovf_desc = "Created by Image Factory"
        else:
            self.ovf_desc = ovf_desc

        self.pool_id = pool_id

    def generate_ovf_xml(self):
        etroot = ElementTree.Element('ovf:Envelope')
        etroot.set('xmlns:ovf', "http://schemas.dmtf.org/ovf/envelope/1/")
        etroot.set('xmlns:rasd', "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData")
        etroot.set('xmlns:vssd', "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData")
        etroot.set('xmlns:xsi', "http://www.w3.org/2001/XMLSchema-instance")
        etroot.set('ovf:version', "0.9")

        etref = ElementTree.Element('References')

        etfile = ElementTree.Element('File')
        etfile.set('ovf:href', str(self.img_uuid)+'/'+str(self.vol_uuid))
        etfile.set('ovf:id', str(self.vol_uuid))
        etfile.set('ovf:size', str(self.disk.vol_size))
        # TODO: Bulk this up a bit
        etfile.set('ovf:description', self.ovf_name)
        etref.append(etfile)

        etroot.append(etref)

        etsec = ElementTree.Element('Section')
        etsec.set('xsi:type', "ovf:NetworkSection_Type")
        ete = ElementTree.Element('Info')
        ete.text = "List of Networks"
        etsec.append(ete)
        # dummy section, even though we have Ethernet defined below
        etroot.append(etsec)

        etsec = ElementTree.Element('Section')
        etsec.set('xsi:type', "ovf:DiskSection_Type")

        etdisk = ElementTree.Element('Disk')
        etdisk.set('ovf:diskId', str(self.vol_uuid))
        vol_size_str = str((self.disk.vol_size + (1024*1024*1024) - 1) / (1024*1024*1024))
        etdisk.set('ovf:size', vol_size_str)
        etdisk.set('ovf:vm_snapshot_id', '00000000-0000-0000-0000-000000000000')
        etdisk.set('ovf:actual_size', vol_size_str)
        etdisk.set('ovf:format', 'http://www.vmware.com/specifications/vmdk.html#sparse')
        etdisk.set('ovf:parentRef', '')
        # XXX ovf:vm_snapshot_id
        etdisk.set('ovf:fileRef', str(self.img_uuid)+'/'+str(self.vol_uuid))
        # XXX ovf:format ("usually url to the specification")
        if self.disk.qcow_size:
            etdisk.set('ovf:volume-type', "Sparse")
            etdisk.set('ovf:volume-format', "COW")
        else:
            etdisk.set('ovf:volume-type', "Preallocated")
            etdisk.set('ovf:volume-format', "RAW")
        etdisk.set('ovf:disk-interface', "VirtIO")
        etdisk.set('ovf:disk-type', "System")
        etdisk.set('ovf:boot', "true")
        etdisk.set('ovf:wipe-after-delete', "false")
        etsec.append(etdisk)

        etroot.append(etsec)

        etcon = ElementTree.Element('Content')
        etcon.set('xsi:type', "ovf:VirtualSystem_Type")
        etcon.set('ovf:id', "out")

        ete = ElementTree.Element('Name')
        ete.text = self.ovf_name
        etcon.append(ete)

        ete = ElementTree.Element('TemplateId')
        ete.text = str(self.tpl_uuid)
        etcon.append(ete)

        # spec also has 'TemplateName'

        ete = ElementTree.Element('Description')
        ete.text = self.ovf_desc
        etcon.append(ete)

        ete = ElementTree.Element('Domain')
        # AD domain, not in use right now
        # ete.text =
        etcon.append(ete)

        ete = ElementTree.Element('CreationDate')
        ete.text = time.strftime("%Y/%m/%d %H:%M:%S", self.disk.create_time)
        etcon.append(ete)

        ete = ElementTree.Element('TimeZone')
        # ete.text =
        etcon.append(ete)

        ete = ElementTree.Element('IsAutoSuspend')
        ete.text = "false"
        etcon.append(ete)

        ete = ElementTree.Element('VmType')
        ete.text = "1"
        etcon.append(ete)

        ete = ElementTree.Element('default_display_type')
        # vnc = 0, gxl = 1
        ete.text = "0"
        etcon.append(ete)

        ete = ElementTree.Element('default_boot_sequence')
        # C=0,   DC=1,  N=2, CDN=3, CND=4, DCN=5, DNC=6, NCD=7,
        # NDC=8, CD=9, D=10, CN=11, DN=12, NC=13, ND=14
        # (C - HardDisk, D - CDROM, N - Network)
        ete.text = "1"
        etcon.append(ete)

        etsec = ElementTree.Element('Section')
        etsec.set('xsi:type', "ovf:OperatingSystemSection_Type")
        etsec.set('ovf:id', str(self.tpl_uuid))
        etsec.set('ovf:required', "false")

        ete = ElementTree.Element('Info')
        ete.text = "Guest OS"
        etsec.append(ete)

        ete = ElementTree.Element('Description')
        # This is rigid, must be "Other", "OtherLinux", "RHEL6", or such
        ete.text = "OtherLinux"
        etsec.append(ete)

        etcon.append(etsec)

        etsec = ElementTree.Element('Section')
        etsec.set('xsi:type', "ovf:VirtualHardwareSection_Type")

        ete = ElementTree.Element('Info')
        ete.text = "1 CPU, 512 Memory"
        etsec.append(ete)

        etsys = ElementTree.Element('System')
        # This is probably wrong, needs actual type.
        ete = ElementTree.Element('vssd:VirtualSystemType')
        ete.text = "RHEVM 4.6.0.163"
        etsys.append(ete)
        etsec.append(etsys)

        etitem = ElementTree.Element('Item')

        ete = ElementTree.Element('rasd:Caption')
        ete.text = "1 virtual CPU"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:Description')
        ete.text = "Number of virtual CPU"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:InstanceId')
        ete.text = "1"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ResourceType')
        ete.text = "3"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:num_of_sockets')
        ete.text = "1"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:cpu_per_socket')
        ete.text = "1"
        etitem.append(ete)

        etsec.append(etitem)

        etitem = ElementTree.Element('Item')

        ete = ElementTree.Element('rasd:Caption')
        ete.text = "512 MB of memory"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:Description')
        ete.text = "Memory Size"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:InstanceId')
        ete.text = "2"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ResourceType')
        ete.text = "4"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:AllocationUnits')
        ete.text = "MegaBytes"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:VirtualQuantity')
        ete.text = "512"
        etitem.append(ete)

        etsec.append(etitem)

        etitem = ElementTree.Element('Item')

        ete = ElementTree.Element('rasd:Caption')
        ete.text = "Drive 1"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:InstanceId')
        ete.text = str(self.vol_uuid)
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ResourceType')
        ete.text = "17"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:HostResource')
        ete.text = str(self.img_uuid)+'/'+str(self.vol_uuid)
        etitem.append(ete)

        ete = ElementTree.Element('rasd:Parent')
        ete.text = "00000000-0000-0000-0000-000000000000"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:Template')
        ete.text = "00000000-0000-0000-0000-000000000000"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ApplicationList')
        # List of installed applications, separated by comma
        etitem.append(ete)

        # This corresponds to ID of volgroup in host where snapshot was taken.
        # Obviously we have nothing like it.
        ete = ElementTree.Element('rasd:StorageId')
        # "Storage Domain Id"
        ete.text = "00000000-0000-0000-0000-000000000000"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:StoragePoolId')
        ete.text = self.pool_id
        etitem.append(ete)

        ete = ElementTree.Element('rasd:CreationDate')
        ete.text = time.strftime("%Y/%m/%d %H:%M:%S", self.disk.create_time)
        etitem.append(ete)

        ete = ElementTree.Element('rasd:LastModified')
        ete.text = time.strftime("%Y/%m/%d %H:%M:%S", self.disk.create_time)
        etitem.append(ete)

        etsec.append(etitem)

        etitem = ElementTree.Element('Item')

        ete = ElementTree.Element('rasd:Caption')
        ete.text = "Ethernet 0 rhevm"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:InstanceId')
        ete.text = "3"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ResourceType')
        ete.text = "10"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ResourceSubType')
        # e1000 = 2, pv = 3
        ete.text = "3"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:Connection')
        ete.text = "rhevm"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:Name')
        ete.text = "eth0"
        etitem.append(ete)

        # also allowed is "MACAddress"

        ete = ElementTree.Element('rasd:speed')
        ete.text = "1000"
        etitem.append(ete)

        etsec.append(etitem)

        etitem = ElementTree.Element('Item')

        ete = ElementTree.Element('rasd:Caption')
        ete.text = "Graphics"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:InstanceId')
        # doc says "6", reality is "5"
        ete.text = "5"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:ResourceType')
        ete.text = "20"
        etitem.append(ete)

        ete = ElementTree.Element('rasd:VirtualQuantity')
        ete.text = "1"
        etitem.append(ete)

        etsec.append(etitem)

        etcon.append(etsec)

        etroot.append(etcon)

        et = ElementTree.ElementTree(etroot)
        return et


class OVFPackage(object):
    '''A directory containing an OVF descriptor and related files such as disk images'''
    def __init__(self, disk, path=None):
        if path:
            self.path = path
        else:
            storage_path = PersistentImageManager.default_manager().storage_path
            self.path = tempfile.mkdtemp(dir=storage_path)

        self.disk = disk

    def delete(self):
        rmtree(self.path, ignore_errors=True)

    def sync(self):
        '''Copy disk image to path, regenerate OVF descriptor'''
        self.copy_disk()
        self.ovf_descriptor = self.new_ovf_descriptor()

        ovf_xml = self.ovf_descriptor.generate_ovf_xml()

        try:
            os.makedirs(os.path.dirname(self.ovf_path))
        except OSError, e:
            if "File exists" not in e:
                raise

        ovf_xml.write(self.ovf_path)

    def make_ova_package(self, gzip=False):
        self.sync()

        mode = 'w' if not gzip else 'w|gz'
        ovapath = os.path.join(self.path, "ova")
        tar = tarfile.open(ovapath, mode)
        cwd = os.getcwd()
        os.chdir(self.path)
        files = glob.glob('*')
        files.remove(os.path.basename(ovapath))

        # per specification, the OVF descriptor must be first in
        # the archive, and the manifest if present must be second
        # in the archive
        for f in files:
            if f.endswith(".ovf"):
                tar.add(f)
                files.remove(f)
                break
        for f in files:
            if f.endswith(".MF"):
                tar.add(f)
                files.remove(f)
                break

        # everything else last
        for f in files:
            tar.add(f)

        os.chdir(cwd)
        tar.close()

        return ovapath


class RHEVOVFPackage(OVFPackage):
    def __init__(self, disk, path=None, ovf_name=None, ovf_desc=None):
        disk = RHEVDisk(disk)
        super(RHEVOVFPackage, self).__init__(disk, path)
        # We need these three unique identifiers when generating XML and the meta file
        self.img_uuid = str(uuid.uuid4())
        self.vol_uuid = str(uuid.uuid4())
        self.tpl_uuid = str(uuid.uuid4())
        self.image_dir = os.path.join(self.path, "images",
                                      self.img_uuid)
        self.disk_path = os.path.join(self.image_dir,
                                      self.vol_uuid)
        self.meta_path = self.disk_path + ".meta"
        self.ovf_dir  = os.path.join(self.path, "master", "vms",
                                     self.tpl_uuid)
        self.ovf_path = os.path.join(self.ovf_dir,
                                     self.tpl_uuid + '.ovf')

        self.ovf_name = ovf_name
        self.ovf_desc = ovf_desc


    def new_ovf_descriptor(self):
        return RHEVOVFDescriptor(img_uuid=self.img_uuid,
                                 vol_uuid=self.vol_uuid,
                                 tpl_uuid=self.tpl_uuid,
                                 ovf_name=self.ovf_name,
                                 ovf_desc=self.ovf_desc,
                                 disk=self.disk)

    def copy_disk(self):
        os.makedirs(os.path.dirname(self.disk_path))
        copyfile_sparse(self.disk.path, self.disk_path)

    def sync(self):
        super(RHEVOVFPackage, self).sync()
        self.meta_file = RHEVMetaFile(self.img_uuid, self.disk)
        meta = open(self.meta_path, 'w')
        meta.write(self.meta_file.generate_meta_file())
        meta.close()

    def make_ova_package(self):
        return super(RHEVOVFPackage, self).make_ova_package(gzip=True)


class RHEVMetaFile(object):
    def __init__(self,
                 img_uuid,
                 disk,
                 storage_domain="00000000-0000-0000-0000-000000000000",
                 pool_id="00000000-0000-0000-0000-000000000000"):
        self.img_uuid = img_uuid
        self.disk = disk
        self.storage_domain = storage_domain
        self.pool_id = pool_id

    def generate_meta_file(self):
        metafile=""

        metafile += "DOMAIN=" + self.storage_domain + "\n"
        # saved template has VOLTYPE=SHARED
        metafile += "VOLTYPE=LEAF\n"
        metafile += "CTIME=" + str(int(self.disk.raw_create_time)) + "\n"
        # saved template has FORMAT=COW
        if self.disk.qcow_size:
            metafile += "FORMAT=COW\n"
        else:
            metafile += "FORMAT=RAW\n"
        metafile += "IMAGE=" + str(self.img_uuid) + "\n"
        metafile += "DISKTYPE=1\n"
        metafile += "PUUID=00000000-0000-0000-0000-000000000000\n"
        metafile += "LEGALITY=LEGAL\n"
        metafile += "MTIME=" + str(int(self.disk.raw_create_time)) + "\n"
        metafile += "POOL_UUID=" + self.pool_id + "\n"
        # assuming 1KB alignment
        metafile += "SIZE=" + str(self.disk.vol_size/512) + "\n"
        metafile += "TYPE=SPARSE\n"
        metafile += "DESCRIPTION=Uploaded by Image Factory\n"
        metafile += "EOF\n"

        return metafile

class RHEVDisk(object):
    def __init__(self, path):
        self.path = path
        self.qcow_size = self.check_qcow_size()
        if self.qcow_size:
            self.vol_size=self.qcow_size
        else:
            self.vol_size = os.stat(self.path).st_size

        self.raw_create_time = os.path.getctime(self.path)
        self.create_time = time.gmtime(self.raw_create_time)

    def check_qcow_size(self):
        # Detect if an image is in qcow format
        # If it is, return the size of the underlying disk image
        # If it isn't, return none

        # For interested parties, this is the QCOW header struct in C
        # struct qcow_header {
        #    uint32_t magic;
        #    uint32_t version;
        #    uint64_t backing_file_offset;
        #    uint32_t backing_file_size;
        #    uint32_t cluster_bits;
        #    uint64_t size; /* in bytes */
        #    uint32_t crypt_method;
        #    uint32_t l1_size;
        #    uint64_t l1_table_offset;
        #    uint64_t refcount_table_offset;
        #    uint32_t refcount_table_clusters;
        #    uint32_t nb_snapshots;
        #    uint64_t snapshots_offset;
        # };

        # And in Python struct format string-ese
        qcow_struct=">IIQIIQIIQQIIQ" # > means big-endian
        qcow_magic = 0x514649FB # 'Q' 'F' 'I' 0xFB

        f = open(self.path,"r")
        pack = f.read(struct.calcsize(qcow_struct))
        f.close()

        unpack = struct.unpack(qcow_struct, pack)

        if unpack[0] == qcow_magic:
            return unpack[5]
        else:
            return None
