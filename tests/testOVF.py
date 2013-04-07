import random
import unittest

from imagefactory_plugins.vSphere import OVF
from tempfile import NamedTemporaryFile

import hashlib
import string
import os

class TestOVF(unittest.TestCase):

    def setUp(self):
        ovf = OVF.OVF()
        ovf.tpl_uuid = "image_id"
        ovf.ovf_desc = 'this file will self destroy the universe'
        ovf.vol_uuid = ''
        ovf.ovf_name = 'lold'
        self.ovf = ovf

    def test_add_image(self, image='/var/lib/imagefactory/storage/2ada6d71-b835-4fa7-a914-c4188e2ce9fa.body'):
        self.ovf.add_image(image, [image])
        assert image in self.ovf.images  #is key in dict?
        assert type(self.ovf.images[image]) == list
        assert image in self.ovf.images[image]

    def _prepare_fake_images(self):
        anum = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        s = ''.join(random.choice(anum) for x in range(16))

        fake_img = NamedTemporaryFile()
        fake_img.write(s)
        fake_img.flush()

        digest = hashlib.sha256(s).hexdigest()

        return fake_img, digest

    def _prepare_manifest_input(self):
        fake_img, digest = self._prepare_fake_images()

        self.test_add_image(fake_img.name)

        assert type(self.ovf.images) == dict
        assert not self.ovf.images.keys() == []

        return fake_img, digest

    def test_generate_manifest_data(self):
        fake_img, digest = self._prepare_manifest_input()
        mf = self.ovf.generate_manifest_data()

        fake_img.close() #yes, this is not guaranteed to happen
        assert not mf == ''
        assert digest in mf

    def test_generate_manifest(self):
        fake_img, _ = self._prepare_manifest_input()
        self.ovf.generate_manifest()

        fake_img.close() #yes, this is not guaranteed to happen
        os.path.isfile('/tmp/manifest.mf')


    def test_save_as(self):
        with NamedTemporaryFile(delete=False) as f:
        #fname = 'test.ovf'
            self.ovf.save_as(f.name)
            print f.name



#     def test_shuffle(self):
#         # make sure the shuffled sequence does not lose any elements
#         random.shuffle(self.seq)
#         self.seq.sort()
#         self.assertEqual(self.seq, range(10))
# 
#         # should raise an exception for an immutable sequence
#         self.assertRaises(TypeError, random.shuffle, (1,2,3))
# 
#     def test_choice(self):
#         element = random.choice(self.seq)
#         self.assertTrue(element in self.seq)
# 
#     def test_sample(self):
#         with self.assertRaises(ValueError):
#             random.sample(self.seq, 20)
#         for element in random.sample(self.seq, 5):
#             self.assertTrue(element in self.seq)

if __name__ == '__main__':
    unittest.main()

