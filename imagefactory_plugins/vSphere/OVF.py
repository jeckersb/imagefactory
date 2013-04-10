#!/usr/bin/python
#
#   Copyright 2011 Red Hat, Inc.
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


import pdb
import logging
import stat
import os
import sys
import struct
import time
import uuid
import subprocess
from tempfile import NamedTemporaryFile
from tempfile import TemporaryFile
from xml.etree import ElementTree

from operator import add
import re
import hashlib

def print_(x):
  print x

class OVF(object):
  def __init__(self):
    self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
    self.log.debug = print_
    self.img_uuid = None
    self.vol_uuid = None
    self.vol_size = None
    self.ovf_name = None #set

    self.qcow_size = None # B! [spare - cow, prealloc - raw]
    self.tpl_uuid = None #set
    self.ovf_desc = None #set
    self.create_time = time.localtime()   #set   # :: Time

#    self.raw_create_time = None
#    self.storage_domain = None
    self.pool_id = 'default'

    self.images = {}
    self.sizes  = {}
    self.real_sizes  = {}

  def add_image(self, img, volume_parts):
    st = os.stat(img)
    self.create_time = time.localtime()
    self.vol_size = st.st_size
    if img in self.images:
      self.images[img].extend(volume_parts)
      self.sizes[img].extend(
          map(lambda x: os.stat(x).st_size, volume_parts)
          )
      self.real_sizes[img].extend(
          map(lambda x: os.stat(x).st_blocks*512, volume_parts)
          )
    else:
      self.images[img] = volume_parts
      self.sizes[img] = map(lambda x: os.stat(x).st_size, volume_parts)
      self.real_sizes[img] = map(lambda x: os.stat(x).st_blocks*512, volume_parts)

  def save_as(self, path):
    self.log.debug('GENERATING MANIFEST')
    self.generate_manifest()
    self.log.debug('MANIFEST DONE')

    ovf_file_object = NamedTemporaryFile(delete=False)
    et = self.generate_ovf_xml()
    et.write(ovf_file_object)
    ovf_file_object.flush()
#    self.copy_as_nfs_user(ovf_file_object.name, self.ovfdest)
    self.log.debug("OVF_FILE_NAME = '%s'" % (ovf_file_object.name))
    os.rename(ovf_file_object.name, path)
    ovf_file_object.close()

  def generate_meta_file(self):
    metafile=""

    metafile += "DOMAIN=" + self.storage_domain + "\n"
    # saved template has VOLTYPE=SHARED
    metafile += "VOLTYPE=LEAF\n"
    metafile += "CTIME=" + str(int(self.raw_create_time)) + "\n"
    # saved template has FORMAT=COW
    if self.qcow_size:
      metafile += "FORMAT=COW\n"
    else:
      metafile += "FORMAT=RAW\n"
    metafile += "IMAGE=" + str(self.img_uuid) + "\n"
    metafile += "DISKTYPE=1\n"
    metafile += "PUUID=00000000-0000-0000-0000-000000000000\n"
    metafile += "LEGALITY=LEGAL\n"
    metafile += "MTIME=" + str(int(self.raw_create_time)) + "\n"
    metafile += "POOL_UUID=" + self.pool_id + "\n"
    # assuming 1KB alignment
    metafile += "SIZE=" + str(self.vol_size/512) + "\n"
    metafile += "TYPE=SPARSE\n"
    metafile += "DESCRIPTION=Uploaded by Image Factory\n"
    metafile += "EOF\n"

    return metafile

  def generate_manifest(self):
    fout = NamedTemporaryFile(delete=False)
    # hashlib is stupid so we can't use map :(
    mf = self.generate_manifest_data() 
    fout.write(mf)
    self.log.debug("NAME %s" % fout.name)
    os.rename(fout.name, '/tmp/manifest.mf')

  def generate_manifest_data(self):
    shas = []
    mf = ''
    for vols in self.images.keys():
      for img in self.images[vols]:
        with open(img, 'rb') as fin:
          digest = hashlib.sha256(fin.read()).hexdigest()
          mf += "SHA256(%s)= %s\n" % (img, digest)

    return mf

  def _gen_disk_elems(self):
    disks = []
    for img in self.images:
      etdisk = ElementTree.Element('Disk')
      etdisk.set('ovf:diskId', str(img))
      vol_size_str = ''#str((self.vol_size + (1024*1024*1024) - 1) / (1024*1024*1024))
      etdisk.set('ovf:size', reduce(add, self.sizes[img]))
      etdisk.set('ovf:vm_snapshot_id', '00000000-0000-0000-0000-000000000000')
      etdisk.set('ovf:actual_size', reduce(add, self.real_sizes[img]))
      etdisk.set('ovf:format', 'http://www.vmware.com/specifications/vmdk.html#sparse')
      etdisk.set('ovf:parentRef', '')
      # XXX ovf:vm_snapshot_id
      etdisk.set('ovf:fileRef', str(img))
      # XXX ovf:format ("usually url to the specification")
      etdisk.set('ovf:volume-type', "Sparse")
      etdisk.set('ovf:volume-format', "COW")
#      if self.qcow_size:
#          etdisk.set('ovf:volume-type', "Sparse")
#          etdisk.set('ovf:volume-format', "COW")
#      else:
#          etdisk.set('ovf:volume-type', "Preallocated")
#          etdisk.set('ovf:volume-format', "RAW")
      ###########################################################################
      etdisk.set('ovf:disk-interface', "VirtIO")
      etdisk.set('ovf:disk-type', "System")
      etdisk.set('ovf:boot', "true")
      etdisk.set('ovf:wipe-after-delete', "false")
      disks.append(etdisk)

    return disks

  def _gen_file_elems(self):
    files = []
    for img in self.images:
      etfile = ElementTree.Element('File')
      etfile.set('ovf:href', str(img)) #+'/'+str(self.vol_uuid))
      etfile.set('ovf:id', str(img))
      etfile.set('ovf:size', str(self.sizes[img]))
      # TODO: Bulk this up a bit
#      etfile.set('ovf:description', self.ovf_name)
      files.append(etfile)
    return files

  def generate_ovf_xml(self):
    etroot = ElementTree.Element('ovf:Envelope')
    etroot.set('xmlns:ovf', "http://schemas.dmtf.org/ovf/envelope/1/")
    etroot.set('xmlns:rasd', "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData")
    etroot.set('xmlns:vssd', "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData")
    etroot.set('xmlns:xsi', "http://www.w3.org/2001/XMLSchema-instance")
    etroot.set('ovf:version', "0.9")

    etref = ElementTree.Element('References')
    files = self._gen_file_elems()
    for etfile in files:
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
    disks = self._gen_disk_elems()
    for disk in disks:
      etsec.append(disk)
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
    ete.text = time.strftime("%Y/%m/%d %H:%M:%S", self.create_time)
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
    ete.text = "vSphere"
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
    ete.text = time.strftime("%Y/%m/%d %H:%M:%S", self.create_time)
    etitem.append(ete)

    ete = ElementTree.Element('rasd:LastModified')
    ete.text = time.strftime("%Y/%m/%d %H:%M:%S", self.create_time)
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
