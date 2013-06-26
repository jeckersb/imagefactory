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

import hashlib
import json
import os
from string import Template
from oz.ozutil import copyfile_sparse
from imgfac.ApplicationConfiguration import ApplicationConfiguration
from common import Common

class VSphere(Common):
    reftpl = '<File ovf:href="$vmdkname" ovf:id="file1" ovf:size="$filemaxsize"/>'
    disktpl = '<Disk ovf:capacity="$capacity" ovf:capacityAllocationUnits="byte" ovf:diskId="vmdisk1" ovf:fileRef="file1" ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized" ovf:populatedSize="$populsize"/>'

    def __init__(self, base_image, image, parameters):
        super(VSphere, self).__init__(base_image, image, parameters)
        self.manifest = os.path.join(self.outdir, 'MANIFEST.MF')
        self.outbody = os.path.join(self.outdir, os.path.basename(self.image.data))
        self.outovf = os.path.join(self.outdir, self.image.identifier + ".ovf")

        try:
            self.template = ApplicationConfiguration().configuration['ova_templates']['vsphere']
        except KeyError:
            self.template = "/etc/imagefactory/ova_templates/ova_vsphere.xml"

    def construct_manifest(self):
        mf = ''

        for img in (self.outbody, self.outovf):
            self.log.info("Calculating hash for %s" % img)
            with open(img, 'rb') as fin:
                digest = hashlib.sha1()
                while True:
                    r = fin.read(1024*1024)
                    if r == '':
                        break
                    digest.update(r)

                digest_str = digest.hexdigest()
                mf += "SHA1(%s)= %s\n" % (os.path.basename(img), digest_str)

        with open(self.manifest, 'w+') as fout:
            fout.write(mf)


    def construct_ref(self):
        size = os.stat(self.base_image.data).st_size

        d = {'vmdkname': os.path.basename(self.image.data),
             'filemaxsize': str(size)}
        tpl = Template(self.reftpl)
        return tpl.substitute(d)


    def construct_disk(self):
        size = os.stat(self.base_image.data).st_size
        sparsesize = os.stat(self.image.data).st_blocks*512

        d = {'capacity': str(size), 'populsize': str(sparsesize)}
        tpl = Template(self.disktpl)
        return tpl.substitute(d)


    def generate(self):
        copyfile_sparse(self.image.data, self.outbody)

        f = self.construct_fragments()

        with open(self.template) as ftpl:
            tpl = Template(ftpl.read())

        outtpl = tpl.substitute(f)

        with open(self.outovf, "w+") as ofil:
            ofil.write(outtpl)

        self.construct_manifest()
        self.create_archive()
