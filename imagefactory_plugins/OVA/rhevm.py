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

import json
import uuid
import os
import time
from string import Template
from oz.ozutil import copyfile_sparse
from imgfac.ApplicationConfiguration import ApplicationConfiguration
from common import Common

class RHEVM(Common):
    reftpl = '<File ovf:href="$href" ovf:id="$id" ovf:size="$size" ovf:description=""/>'
    disktpl = '<Disk ovf:diskId="$diskId" ovf:size="$size" ovf:actual_size="$actual_size" ovf:vm_snapshot_id="00000000-0000-0000-0000-000000000000" ovf:parentRef="" ovf:fileRef="$fileRef" ovf:format="http://www.gnome.org/~markmc/qcow-image-format.html" ovf:volume-format="COW" ovf:volume-type="Sparse" ovf:disk-interface="VirtIO" ovf:boot="true" ovf:disk-alias="a4722eec-fa42-4054-977f-7e09e06dbf3a_Disk1" ovf:wipe-after-delete="false"/>'
    diskitemtpl = '''<Item>
        <rasd:Caption>
        b57db30f-070f-4173-bf6a-333ae9a247b0_Disk1</rasd:Caption>
        <rasd:InstanceId>$id</rasd:InstanceId>
        <rasd:ResourceType>17</rasd:ResourceType>
        <rasd:HostResource>$group_id/$id</rasd:HostResource>
        <rasd:Parent>
        00000000-0000-0000-0000-000000000000</rasd:Parent>
        <rasd:Template>
        00000000-0000-0000-0000-000000000000</rasd:Template>
        <rasd:ApplicationList></rasd:ApplicationList>
        <rasd:StorageId>
        c256eb74-a127-48d5-9321-a6bbcf354326</rasd:StorageId>
        <rasd:StoragePoolId>
        b9bb11c2-f397-4f41-a57b-7ac15a894779</rasd:StoragePoolId>
        <rasd:CreationDate>2013/05/23 19:31:52</rasd:CreationDate>
        <rasd:LastModified>2013/05/23 19:31:54</rasd:LastModified>
        <Type>disk</Type>
        <Device>disk</Device>
        <rasd:Address></rasd:Address>
        <BootOrder>0</BootOrder>
        <IsPlugged>true</IsPlugged>
        <IsReadOnly>false</IsReadOnly>
        <Alias></Alias>
      </Item>'''


    def __init__(self, base_image, image, parameters):
        super(RHEVM, self).__init__(base_image, image, parameters)
        self.image_group_identifier = str(uuid.uuid1())
        self.vm_identifier = str(uuid.uuid1())

        self.outbody = os.path.join(self.outdir, "images",
                                    self.image_group_identifier,
                                    self.image.identifier)

        self.metafile = self.outbody + '.meta'

        self.outovf = os.path.join(self.outdir, "master", "vms",
                                   self.vm_identifier,
                                   self.vm_identifier + ".ovf")

        try:
            self.template = ApplicationConfiguration().configuration['ova_templates']['rhevm']
        except KeyError:
            self.template = "/etc/imagefactory/ova_templates/ova_rhevm.xml"


    def construct_metafile(self):
        meta='''\
DOMAIN=00000000-0000-0000-0000-000000000000
VOLTYPE=LEAF
CTIME=%(time)s
FORMAT=COW
IMAGE=%(image)s
DISKTYPE=1
PUUID=00000000-0000-0000-0000-000000000000
LEGALITY=LEGAL
MTIME=%(time)s
POOL_UUID=00000000-0000-0000-0000-000000000000
SIZE=%(size)s
TYPE=SPARSE
DESCRIPTION=Created by imagefactory
'''  % {"time": str(time.time()),
        "image": self.image_group_identifier,
        "size": os.stat(self.image.data).st_size}

        with open(self.metafile, 'w+') as f:
            f.write(meta)

    def construct_ref(self):
        size = os.stat(self.base_image.data).st_size

        d = {'href': os.path.join(self.image_group_identifier,
                                  self.image.identifier),
             'id': self.image.identifier,
             'size': str(size)}
        tpl = Template(self.reftpl)
        return tpl.substitute(d)


    def construct_disk(self):
        size = os.stat(self.base_image.data).st_size
        sparsesize = os.stat(self.image.data).st_blocks*512

        d = {'diskId': self.image.identifier,
             'size': str(size >> 30), #in GB, not bytes
             'actual_size': str(sparsesize >> 30), #likewise
             'fileRef': self.image.identifier}
        tpl = Template(self.disktpl)
        return tpl.substitute(d)


    def construct_diskitem(self):
        d = {'id': self.image.identifier,
             'group_id': self.image_group_identifier}
        tpl = Template(self.diskitemtpl)
        return tpl.substitute(d)


    def make_tree(self):
        '''
        doc taken from ovirt-image-uploader
        The image uploader can be used to list export storage domains and upload OVF files to
        export storage domains. This tool only supports OVF files created by oVirt engine.  OVF archives should have the
        following characteristics:
        1. The OVF archive must be created with gzip compression.
        2. The archive must have the following internal layout:
        |-- images
        |   |-- <Image Group UUID>
        |        |--- <Image UUID (this is the disk image)>
        |        |--- <Image UUID (this is the disk image)>.meta
        |-- master
        |   |---vms
        |       |--- <UUID>
        |             |--- <UUID>.ovf
        '''
        os.makedirs(os.path.dirname(self.outbody))
        os.makedirs(os.path.dirname(self.outovf))

    def generate(self):
        self.make_tree()
        copyfile_sparse(self.image.data, self.outbody)

        f = self.construct_fragments()

        with open(self.template) as ftpl:
            tpl = Template(ftpl.read())

        outtpl = tpl.substitute(f)

        with open(self.outovf, 'w+') as ofil:
            ofil.write(outtpl)


        self.construct_metafile()
        self.create_archive(gzip=True)
