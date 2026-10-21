"""
Gera um certificado HTTPS autoassinado (certificado/cert.pem e certificado/chave.pem).

Só é necessário quando o servidor roda em OUTRA máquina (VPS): os navegadores
só liberam o microfone em páginas "seguras" (localhost ou HTTPS).
Depois de gerar, ative em config.json:  "https": {"ativo": true, ...}
Na primeira abertura o navegador avisa que o certificado não é reconhecido;
clique em "Avançado" e "Continuar".

Uso: python instalacao/gerar_certificado.py [--nome meu-servidor.exemplo.com] [--ip 203.0.113.10]
"""

import argparse
import ipaddress
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nome", action="append", default=[], help="nome de host (pode repetir)")
    ap.add_argument("--ip", action="append", default=[], help="endereço IP (pode repetir)")
    ap.add_argument("--dias", type=int, default=3650)
    args = ap.parse_args()

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("Falta o pacote 'cryptography'. Instale com:  .venv\\Scripts\\python.exe -m pip install cryptography")
        return 1

    pasta = RAIZ / "certificado"
    pasta.mkdir(exist_ok=True)
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nomes = args.nome or ["localhost"]
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nomes[0]),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "GMP Tradutor")])
    san = [x509.DNSName(n) for n in nomes] + [x509.DNSName("localhost")]
    for ip in args.ip + ["127.0.0.1"]:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            print(f"IP inválido ignorado: {ip}")
    agora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome).issuer_name(nome).public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1)).not_valid_after(agora + timedelta(days=args.dias))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(chave, hashes.SHA256())
    )
    (pasta / "chave.pem").write_bytes(chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    (pasta / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Certificado gerado em {pasta} (válido por {args.dias} dias) para: {', '.join(nomes)} {', '.join(args.ip)}")
    print('Agora ative no config.json:  "https": {"ativo": true, ...}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
