"""Microsoft Entra ID client-credentials flow with a certificate (no client secret).

The service principal proves its identity with a JWT client assertion signed by
its private key; Entra ID checks the signature against the certificate uploaded
to the app registration. Key and certificate are mounted from Key Vault through
the Secrets Store CSI driver and never appear in configuration or code.

This is the identity half of the transport protection. The network half is the
private endpoint: Document Intelligence and Azure OpenAI have public network
access disabled, so the token is only usable from inside the virtual network.
"""

from __future__ import annotations

import base64
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


def pem_block(data: bytes, label: str) -> bytes:
    """Return the first PEM block whose label ends with ``label`` (e.g. "PRIVATE KEY", "CERTIFICATE")."""
    match = re.search(rb"-----BEGIN ([A-Z ]*" + label.encode() + rb")-----.+?-----END \1-----", data, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"no {label} block found")
    return match.group(0) + b"\n"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class CertificateCredential:
    tenant_id: str
    client_id: str
    private_key_pem: bytes
    certificate_pem: bytes
    scope: str = COGNITIVE_SCOPE
    authority: str = "https://login.microsoftonline.com"
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=30))
    _token: str | None = field(default=None, init=False, repr=False)
    _expires_at: float = field(default=0.0, init=False, repr=False)

    @classmethod
    def from_files(
        cls, tenant_id: str, client_id: str, key_path: Path, cert_path: Path, **kwargs: object
    ) -> CertificateCredential:
        """Key and certificate may be two files or one PEM bundle (as Key Vault's CSI driver mounts it)."""
        key = pem_block(key_path.read_bytes(), "PRIVATE KEY")
        certificate = pem_block(cert_path.read_bytes(), "CERTIFICATE")
        return cls(tenant_id, client_id, key, certificate, **kwargs)  # type: ignore[arg-type]

    @property
    def token_endpoint(self) -> str:
        return f"{self.authority}/{self.tenant_id}/oauth2/v2.0/token"

    def client_assertion(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        certificate = x509.load_pem_x509_certificate(self.certificate_pem)
        thumbprint = certificate.fingerprint(hashes.SHA256())
        header = {"alg": "PS256", "typ": "JWT", "x5t#S256": _b64url(thumbprint)}
        claims = {
            "aud": self.token_endpoint,
            "iss": self.client_id,
            "sub": self.client_id,
            "jti": str(uuid.uuid4()),
            "nbf": int(now),
            "iat": int(now),
            "exp": int(now) + 600,
        }
        signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
        key = serialization.load_pem_private_key(self.private_key_pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("an RSA private key is required")
        signature = key.sign(
            signing_input.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return f"{signing_input}.{_b64url(signature)}"

    def __call__(self) -> str:
        """Return a cached bearer token, refreshing it five minutes before expiry."""
        if self._token and time.time() < self._expires_at - 300:
            return self._token
        response = self.client.post(
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "scope": self.scope,
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": self.client_assertion(),
            },
        )
        response.raise_for_status()
        body = response.json()
        self._token = str(body["access_token"])
        self._expires_at = time.time() + float(body.get("expires_in", 3600))
        return self._token
