from __future__ import annotations

import unittest

from core import asymmetric_signing
from core.key_manager import KeyManager


class TestKeyManager(unittest.TestCase):
    def test_hmac_sign_verify_rotate_remove(self):
        km = KeyManager()
        name = "test-hmac"
        priv = b"supersecret"
        pub = b"supersecret"

        km.register_private_key(name, priv)
        km.register_public_key(name, pub)

        payload = b"hello world"
        sig = km.sign(name, payload)
        self.assertTrue(km.verify(name, payload, sig))

        # rotate key
        new_priv = b"newsuper"
        new_pub = b"newsuper"
        km.rotate_key(name, new_priv, new_pub)
        sig2 = km.sign(name, payload)
        self.assertTrue(km.verify(name, payload, sig2))

        # export/list/remove
        self.assertIn(name, km.list_keys())
        self.assertIsNotNone(km.export_public(name))
        km.remove_key(name)
        self.assertNotIn(name, km.list_keys())

    def test_crypto_sign_verify_if_available(self):
        if not asymmetric_signing._HAS_CRYPTO:
            self.skipTest("cryptography not available; skipping crypto path test")

        # create an in-memory RSA keypair
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub = priv.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        km = KeyManager()
        name = "rsa-test"
        km.register_private_key(name, priv_pem)
        km.register_public_key(name, pub_pem)

        payload = b"verify me"
        sig = km.sign(name, payload)
        self.assertTrue(km.verify(name, payload, sig))


if __name__ == "__main__":
    unittest.main()
