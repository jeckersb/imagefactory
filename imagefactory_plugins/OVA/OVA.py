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

import logging
import uuid
import zope
import inspect
from imgfac.CloudDelegate import CloudDelegate
from imgfac.PersistentImageManager import PersistentImageManager
from imgfac.TargetImage import TargetImage

class OVA(object):
    zope.interface.implements(CloudDelegate)


    def __init__(self):
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def builder_should_create_target_image(self, builder, target, image_id, template, parameters):
        retval = False

        if isinstance(builder.base_image, TargetImage):
            if builder.base_image.target in ('vsphere', 'rhevm'):
                retval = True

        self.log.info('builder_should_create_target_image() called on OVA plugin - returning %s' % retval)

        return retval

    def builder_did_create_target_image(self, builder, target, image_id, template, parameters):
        self.log.info('builder_did_create_target_image() called in OVA plugin')
        self.status="BUILDING"

        self.target_image = builder.base_image
        self.base_image = PersistentImageManager.default_manager().image_with_id(self.target_image.base_image_id)
        self.image = builder.target_image
        self.parameters = parameters

        # This lets our logging helper know what image is being operated on
        self.active_image = self.image

        self.generate_ova()

        self.percent_complete=100
        self.status="COMPLETED"

    def generate_ova(self):
        if self.target_image.target == 'vsphere':
            from vsphere import VSphere
            klass = VSphere
        elif self.target_image.target == 'rhevm':
            from rhevm import RHEVM
            klass = RHEVM
        else:
            raise ImageFactoryException("OVA plugin only support vsphere or rhevm images")

        generator = klass(self.base_image, self.image, self.parameters)
        generator.generate()
        generator.cleanup()
