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

from string import Template
from shutil import rmtree
import os
import tarfile
import tempfile
import glob
import logging

from imgfac.PersistentImageManager import PersistentImageManager

class Common(object):
    def __init__(self, base_image, image, parameters):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.base_image = base_image
        self.image = image
        self.parameters = parameters
        self.outdir = self._tempdir()

    def cleanup(self):
        rmtree(self.outdir, ignore_errors=True)

    def construct_fragments(self):
        return {'filereferencies': self.construct_ref(),
                'disksection': self.construct_disk(),
                'diskitem': self.construct_diskitem()}

    def construct_diskitem(self):
        pass

    def create_archive(self, gzip=False):
        mode = 'w' if not gzip else 'w|gz'
        tar = tarfile.open(self.image.data, mode)
        cwd = os.getcwd()
        os.chdir(self.outdir)
        files = glob.glob('*')

        # per specification, the OVF descriptor must be first in
        # the archive, and the manifest if present must be second
        # in the archive
        for f in files:
            if f.endswith(".ovf"):
                tar.add(f)
                files.remove(f)
        for f in files:
            if f.endswith(".MF"):
                tar.add(f)
                files.remove(f)

        # everything else last
        for f in files:
            tar.add(f)

        os.chdir(cwd)
        tar.close()

    def _tempdir(self):
        storage_path = PersistentImageManager.default_manager().storage_path
        return tempfile.mkdtemp(dir=storage_path)
