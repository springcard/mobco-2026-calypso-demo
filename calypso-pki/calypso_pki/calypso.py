"""Calypso PKI business logic."""

import os
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.exceptions import InvalidSignature

from .callbacks import CalypsoPkiCallbacks
from .channel import ApduChannel
from .constants import *

DEBUG = False
BENCHMARK = False


@dataclass
class CalypsoPkiTransaction:
    card_public_key: bytes | None = None
    ca_certificate: bytes | None = None
    card_certificate: bytes | None = None
    input_data: list[int] | None = None
    signature: bytes | None = None
    communication_time: float = 0.0


class CardUnsupportedError(Exception):
    pass


class CardNotGenuineError(Exception):
    pass


def _call_callback(callbacks, name: str, *args):
    if callbacks is None:
        return None

    callback = getattr(callbacks, name, None)
    if callback is None:
        return None

    return callback(*args)


def _card_not_genuine(callbacks, message: str):
    _call_callback(callbacks, "OnCardNotGenuine")
    raise CardNotGenuineError(message)


"""
Quick'n'dirty ASN.1 DER parser
"""  
def parse_tlv(data):
    i = 0
    tlvs = {}
    raw_fields = {}
    while i < len(data):
        tag_start = i
        tag = data[i]
        i += 1
        if tag in (0x5F, 0x7F, 0xDF):
            tag = (tag << 8) | data[i]
            i += 1

        length = data[i]
        i += 1
        if length & 0x80:  # Long-form length
            num_len_bytes = length & 0x7F
            length = int.from_bytes(data[i:i+num_len_bytes], 'big')
            i += num_len_bytes

        value = data[i:i+length]
        i += length
        tlvs[tag] = value
        raw_fields[tag] = data[tag_start:i]
    return tlvs, raw_fields
      
"""
Parse a Calypso certificate
"""
def print_struct(cert):
    for k, v in cert.items():
        if isinstance(v, int):
            print(f"\t{k}={v:02X}")
        else:
            print(f"\t{k}={bytes(v).hex().upper()}")

def parse_cacert(data: bytes, silent: bool):
    
    if not BENCHMARK and not silent:
        print("Parsing CACert")
        print(f"\t{data.hex().upper()}")
    
    if len(data) != 384:
        print("Length of CA Certificate shall be 384")
        return None
    if data[0] != 0x90:
        print("Type of CA Certificate shall be 0x90")
        return None
        
    result = {}
    offset = 0
    
    result["Type"] = data[offset]
    offset += 1
    result["StructureVersion"] = data[offset]
    offset += 1
    result["IssuerKeyReference"] = data[offset:offset+29]
    offset += 29
    result["CaTargetKeyReference"] = data[offset:offset+29]
    offset += 29
    result["StartDate"] = data[offset:offset+4]
    offset += 4
    result["CaRfu1"] = data[offset:offset+4]
    offset += 4
    result["CaRights"] = data[offset]
    offset += 1
    result["CaScope"] = data[offset]
    offset += 1
    result["EndDate"] = data[offset:offset+4]
    offset += 4
    result["CaTargetAidSize"] = data[offset]
    offset += 1
    result["CaTargetAidValue"] = data[offset:offset+16]
    offset += 16
    result["CaTargetAid"] = result["CaTargetAidValue"][0:result["CaTargetAidSize"]]
    result["CaRfu2"] = data[offset:offset+3]
    offset += 3
    result["CaPublicKeyHeader"] = data[offset:offset+34]
    offset += 34
    result["Signature"] = data[offset:offset+256]
    result["Message"] = data[0:offset]
       
    if not BENCHMARK and not silent:
        print("CACert:")
        print_struct(result)
    return result

def parse_cardcert(data: bytes, silent: bool):
    
    if not BENCHMARK and not silent:
        print("Parsing CardCert")
        print(f"\t{data.hex().upper()}")
    
    if len(data) != 316:
        print("Length of Card Certificate shall be 316")
        return None
    if data[0] != 0x91:
        print("Type of Card Certificate shall be 0x91")
        return None
        
    result = {}    
    offset = 0
    
    result["Type"] = data[offset]
    offset += 1
    result["StructureVersion"] = data[offset]
    offset += 1
    result["IssuerKeyReference"] = data[offset:offset+29]
    offset += 29
    result["CardAidSize"] = data[offset]
    offset += 1
    result["CardAidValue"] = data[offset:offset+16]
    offset += 16
    result["CardAid"] = result["CardAidValue"][0:result["CardAidSize"]]
    result["CardSerialNumber"] = data[offset:offset+8]
    offset += 8
    result["CardIndex"] = data[offset:offset+4]
    offset += 4
    result["Signature"] = data[offset:offset+256]
    result["Message"] = data[0:offset]
       
    if not BENCHMARK and not silent:
        print("CardCert:")
        print_struct(result)
    return result

def parse_cardcert_data(data: bytes, silent: bool):
    if len(data) != 222:
        print("Length of recoverable data shall be 222")
        return None
        
    result = {}
    offset = 0
    
    result["StartDate"] = data[offset:offset+4]
    offset += 4
    result["EndDate"] = data[offset:offset+4]
    offset += 4
    result["CardRights"] = data[offset]
    offset += 1
    result["CardInfo"] = data[offset:offset+7]
    offset += 7
    result["CardRfu"] = data[offset:offset+18]
    offset += 18
    result["EccPublicKey"] = data[offset:offset+64]
    offset += 64
    result["EccRfu"] = data[offset:offset+124]
       
    if not BENCHMARK and not silent:
        print("CardCert data recovered from Signature:")
        print_struct(result)
    return result    

"""
Take a BCD date and translate it to the YYYY-MM-DD format
"""  
def bcd_to_date(b):
    return f"{b[0]>>4}{b[0]&0x0F}{b[1]>>4}{b[1]&0x0F}-{b[2]>>4}{b[2]&0x0F}-{b[3]>>4}{b[3]&0x0F}"

"""
HexToBytes
"""
def h(hexstr: str) -> bytes:
    return bytes.fromhex(''.join(hexstr.split()))    

"""
SHA256
"""   
def sha256(data: bytes) -> bytes:
    hsh = hashes.Hash(hashes.SHA256())
    hsh.update(data)
    return hsh.finalize()

"""
MGF1
"""   
def mgf1(seed: bytes, length: int) -> bytes:
    """MGF1-SHA256, comme dans le doc (7 hachages concaténés ici → tronqués à 223)."""
    out, c = b"", 0
    while len(out) < length:
        out += sha256(seed + c.to_bytes(4, "big"))
        c += 1
    return out[:length]
    
"""
Verify the signature returned by the Calypso card at the end of the session
"""   
def verify_signature_of_session(data: bytes, signature: bytes, public_key: bytes, silent: bool):
    
    if not BENCHMARK and not silent:
        print("Verifying the Signature of the Session bytes")    
        print("\tSession bytes: " + data.hex().upper())
        print("\tSignature computed by the Card: " + signature.hex().upper())
        print("\tPublic Key of the the Card: " + public_key.hex().upper())
    
    """ Create the signature object """
    if len(signature) != 64:
        raise ValueError("Signature (r||s) must be 64-byte long.")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    signature = utils.encode_dss_signature(r, s)
    
    """ Create the public key object """
    if len(public_key) != 64:
        raise ValueError("Public Key (X||Y) must be 64-byte long.")
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b"\x04" + public_key)
   
    """ Verify the signature """
    signature_valid = False       
    try:
        public_key.verify(
            signature,
            data,
            ec.ECDSA(hashes.SHA256())
        )
        if not BENCHMARK and not silent:
            print("The Signature of the Session bytes by the Card is OK")
        signature_valid = True
    except InvalidSignature:
        if not silent:
            print("ERROR: The Signature of the Session bytes by the Card is invalid")
        
    return signature_valid

"""
ISO9792-2 RSA verification, with message recovery
Verify ISO/IEC 9796-2 (trailer 0xBC, MGF1-SHA256) and return the result and the recovered infos
"""
def verify_certificate_iso9796_2(message: bytes, signature: bytes, public_key: bytes, e: int, silent: bool):
    
    if not BENCHMARK and not silent:
        print("Verifying the Signature of the Certificate")    
        print("\tCertificate Message: " + message.hex().upper())
        print("\tSignature provided in the Certificate: " + signature.hex().upper())
        print("\tPublic Key of the the CA: " + public_key.hex().upper())
    
    n = int((public_key.hex()), 16)
    
    if DEBUG:
        print("M2: " + message.hex().upper())

    hash_M2 = sha256(message)    

    if DEBUG:
        print("SHA256(M2): " + hash_M2.hex().upper())
    
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        raise ValueError("Signature length mismatch")

    # 1) « déchiffrement » RSA: Sr = sig^e mod n sur k octets
    s_int = int.from_bytes(signature, "big")
    m_int = pow(s_int, e, n)
    Sr = m_int.to_bytes(k, "big")
    if DEBUG:
        print("Sr: " + Sr.hex().upper())

    # 2) Contrôles structurels
    if Sr[-1] != 0xBC or (Sr[0] >> 7) != 0:
        print("Sr is invalid")
        return False, {}

    # 3) Récupération H* (32 octets à gauche du trailer)
    H_star = Sr[-33:-1]
    if DEBUG:
        print("H*: " + H_star.hex().upper())
    
    # 4) N* = MGF1(H*, 223), D’* = Sr[0:223], D* = N* XOR D’*
    N_star = mgf1(H_star, 223)
    if DEBUG:
        print("N*: " + N_star.hex().upper())
    Dprime_star = Sr[:223]
    if DEBUG:
        print("D'*: " + Dprime_star.hex().upper())
    D_star = bytes(a ^ b for a, b in zip(N_star, Dprime_star))
    if DEBUG:
        print("D*: " + D_star.hex().upper())

    # 5) Après mise à zéro du bit de poids fort, le 1er octet doit valoir 0x01
    if (D_star[0] & 0x7F) != 0x01:
        print("D* is invalid")
        return False, {}

    # 6) M1* = D*[1:] (données récupérées), puis H' = SHA256(len(M1*)_bits || M1* || SHA256(M2*))
    M1_star = D_star[1:]
    if DEBUG:
        print("M1*: " + M1_star.hex().upper())
    
    data = (len(M1_star)*8).to_bytes(8, "big") + M1_star + hash_M2
    if DEBUG:
        print("Input Data: " + data.hex().upper())
    
    H_prime = sha256(data)
    
    if DEBUG:
        print("H': " + H_prime.hex().upper())

    ok = (H_prime == H_star)
    info = {
        "Sr": Sr,
        "H*": H_star,
        "H'": H_prime,
        "M1*": M1_star,
    }
    return ok, info

"""
Verify CardCert against CAPub, and verify that it matches CardPub
"""
def verify_cardcert(cardcert, capub: bytes, silent: bool):  
    ok, info = verify_certificate_iso9796_2(
        bytes(cardcert["Message"]), 
        bytes(cardcert["Signature"]),
        capub,
        RSA_PUB_EXP,
        silent)
        
    if not ok:
        print("Failed to verify CardCert against CAPub")
        return False, None
        
    data_raw = info["M1*"]    
    data_struct = parse_cardcert_data(data_raw, silent)
   
    if data_struct is None:
        print("CardPub recovered from RSA verification against CAPub is invalid")
        return False, None

    if (data_struct["EccPublicKey"] is None) or (len(data_struct["EccPublicKey"]) != 64):
        print("CardPub recovered from RSA verification against CAPub is invalid")
        return False, None

    return True, data_struct["EccPublicKey"]
    
    
"""
Verify CACert against RootPub
"""
def verify_cacert(cacert, rootpub: bytes, silent: bool):
    ok, info = verify_certificate_iso9796_2(
        bytes(cacert["Message"]), 
        bytes(cacert["Signature"]),
        rootpub,
        RSA_PUB_EXP,
        silent)
        
    if not ok:
        print("Failed to verify CACert against RootPub")
        return False, None
               
    data_raw = info["M1*"]
    
    N_left = bytes(cacert["CaPublicKeyHeader"])
    N_right = data_raw    
    N = N_left + N_right
    
    return True, N


def _require_success(sw: int, message: str) -> None:
    if sw != 0x9000:
        raise Exception(message)


def _build_session_input(command1, response1, command2, response2, command3, response3):
    input_data = [0x10]
    input_data = input_data + [len(command1) - 1] + list(command1[:-1])
    input_data = input_data + [len(response1) + 2] + list(response1) + [0x90, 0x00]
    input_data = input_data + [len(command2)] + list(command2)
    input_data = input_data + [len(response2) + 2] + list(response2) + [0x90, 0x00]
    input_data = input_data + [len(command3)] + list(command3)
    input_data = input_data + [len(response3) + 2] + list(response3) + [0x90, 0x00]
    return input_data


def read_calypso_pki_transaction(
    channel: ApduChannel,
    callbacks: CalypsoPkiCallbacks | None = None,
    benchmark: bool = False,
) -> CalypsoPkiTransaction:
    global BENCHMARK

    previous_benchmark = BENCHMARK
    BENCHMARK = benchmark
    try:
        t0 = time.perf_counter()

        _application_fci, sw = channel.transmit(CALYPSO_SELECT_APPLICATION, "SelectApplication")
        if sw != 0x9000:
            _call_callback(callbacks, "OnCardUnsupported")
            raise CardUnsupportedError("SelectApplication failed")

        challenge = list(os.urandom(8))
        command1 = CALYPSO_OPEN_SESSION_AND_READ_ENV_HEADER + challenge + CALYPSO_OPEN_SESSION_AND_READ_ENV_TRAILER
        response1, sw = channel.transmit(command1, "OpenSession(Challenge) and Read Environment")
        _require_success(sw, "ECDSASign failed")

        command2 = CALYPSO_READ_CTC_LIST
        response2, sw = channel.transmit(command2, "Read CTC List")
        _require_success(sw, "Read CTC failed")

        command3 = CALYPSO_READ_CONTRACT
        response3, sw = channel.transmit(command3, "Read Contract")
        _require_success(sw, "Read Contract failed")

        signature, sw = channel.transmit(CALYPSO_CLOSE_SESSION, "CloseSession")
        _require_success(sw, "CloseSession failed")

        input_data = _build_session_input(command1, response1, command2, response2, command3, response3)

        card_public_key, sw = channel.transmit(CALYPSO_GET_CARDPUB, "GetData#CardPub")
        _require_success(sw, "Failed to get CardPub")

        ca_certificate_1, sw = channel.transmit(CALYPSO_GET_CACERT_1, "GetData#CACert#1")
        _require_success(sw, "Failed to get CACert (#1)")

        ca_certificate_2, sw = channel.transmit(CALYPSO_GET_CACERT_2, "GetData#CACert#2")
        _require_success(sw, "Failed to get CACert (#2)")
        ca_certificate = ca_certificate_1 + ca_certificate_2

        card_certificate_1, sw = channel.transmit(CALYPSO_GET_CARDCERT_1, "GetData#CardCert#1")
        _require_success(sw, "Failed to get CardCert (#1)")

        card_certificate_2, sw = channel.transmit(CALYPSO_GET_CARDCERT_2, "GetData#CardCert#2")
        _require_success(sw, "Failed to get CardCert (#2)")
        card_certificate = card_certificate_1 + card_certificate_2

        return CalypsoPkiTransaction(
            card_public_key=card_public_key,
            ca_certificate=ca_certificate,
            card_certificate=card_certificate,
            input_data=input_data,
            signature=signature,
            communication_time=time.perf_counter() - t0,
        )
    finally:
        BENCHMARK = previous_benchmark


def verify_calypso_pki_transaction(
    transaction: CalypsoPkiTransaction,
    callbacks: CalypsoPkiCallbacks | None = None,
    benchmark: bool = False,
) -> float:
    global BENCHMARK

    previous_benchmark = BENCHMARK
    BENCHMARK = benchmark
    try:
        t0 = time.perf_counter()

        card_public_key = transaction.card_public_key
        ca_certificate = transaction.ca_certificate
        card_certificate = transaction.card_certificate
        input_data = transaction.input_data
        signature = transaction.signature

        if (card_public_key is not None) and (input_data is not None) and (signature is not None):
            tlvs, _raw = parse_tlv(card_public_key)
            card_public_key = tlvs.get(0xDF2C)
            if card_public_key is None:
                _card_not_genuine(callbacks, "Format of CardPub is invalid")

            if len(card_public_key) != 64:
                _card_not_genuine(callbacks, "Length of CardPub is invalid")

            if len(signature) != 64:
                _card_not_genuine(callbacks, "Length of Signature is invalid")

            if not verify_signature_of_session(bytes(input_data), bytes(signature), bytes(card_public_key), False):
                _card_not_genuine(callbacks, "Failed to verify Card's Signature over Session data")

            if not BENCHMARK:
                print("The Signature computed by the Card is valid")

        if (card_public_key is not None) and (card_certificate is not None) and (ca_certificate is not None):
            if not BENCHMARK:
                print("Verify PKI")

            tlvs, _raw = parse_tlv(ca_certificate)
            ca_certificate = tlvs.get(0xDF4A)
            if ca_certificate is None:
                _card_not_genuine(callbacks, "Format of CACert is invalid")
            ca_certificate = parse_cacert(ca_certificate, False)
            if ca_certificate is None:
                _card_not_genuine(callbacks, "Format of CACert is invalid")
            ok, ca_public_key = verify_cacert(ca_certificate, bytes(CALYPSO_PUBKEY_TEST), False)
            if not ok:
                _card_not_genuine(callbacks, "Failed to Verify CACert against RootPub / Failed to retrieve CAPub")

            tlvs, _raw = parse_tlv(card_certificate)
            card_certificate = tlvs.get(0xDF4C)
            if card_certificate is None:
                _card_not_genuine(callbacks, "Format of CardCert is invalid")
            card_certificate = parse_cardcert(card_certificate, False)
            if card_certificate is None:
                _card_not_genuine(callbacks, "Format of CardCert is invalid")
            ok, card_public_key_prime = verify_cardcert(card_certificate, ca_public_key, False)
            if not ok:
                _card_not_genuine(callbacks, "Failed to Verify CardCert against CAPub / Failed to retrieve CardPub")
            if bytes(card_public_key) != card_public_key_prime:
                _card_not_genuine(callbacks, "CardCert and retrieved CardPub don't match actual CardPub used for the transaction")

            if not BENCHMARK:
                print("The Card is authentic")

            card_serial_number = bytes(card_certificate["CardSerialNumber"]).hex().upper()
            _call_callback(callbacks, "OnCardRead", card_serial_number)

        return time.perf_counter() - t0
    finally:
        BENCHMARK = previous_benchmark


def run_self_tests() -> None:
    """
    Self-test with the TN325 vectors
    """

    """ Recorded Card transaction """
    tn325_digest = hashes.Hash(hashes.SHA256())
    tn325_digest.update(bytes(TN325_INPUT))
    tn325_input_sha256 = tn325_digest.finalize()
    if tn325_input_sha256 != bytes(TN325_INPUT_SHA256):
        raise Exception("TN325_INPUT is corrupted or TN325_INPUT_SHA256 is wrong")
    if not verify_signature_of_session(bytes(TN325_INPUT), bytes(TN325_SIGNATURE), bytes(TN325_CARDPUB), True):
        raise Exception("TN325 self-test failed (Session)")

    """ Process CACert """
    tn325_cacert = parse_cacert(bytes(TN325_CACERT), True)
    ok, tn325_capub = verify_cacert(tn325_cacert, bytes(CALYPSO_PUBKEY_TEST), True)
    if not ok:
        raise Exception("TN325 self-test failed (verify CACert against RootPub, retrieve CAPub)")
    if not tn325_capub == bytes(TN325_CAPUB):
        raise Exception("Retrieved CAPub is wrong")

    """ Process CardCert """
    tn325_cardcert = parse_cardcert(bytes(TN325_CARDCERT), True)
    ok, tn325_cardpub = verify_cardcert(tn325_cardcert, tn325_capub, True)
    if not ok:
        raise Exception("TN325 self-test failed (verify CardCert against CAPub, retrieve CardPub)")   
    if not tn325_cardpub == bytes(TN325_CARDPUB):
        raise Exception("Retrieved CardPub is wrong")
    
    """
    Test with the sample card
    """

    """ Get CardPub, CardCert and CACert """
    tlvs, raw = parse_tlv(FIRST_DF2C_RESP)
    test_cardpub = tlvs.get(0xDF2C)
    if test_cardpub is None:
        raise Exception("Self-test failed (CAPub)")
    tlvs, raw = parse_tlv(FIRST_DF4A_RESP + FIRST_DF4B_RESP)
    test_cacert = tlvs.get(0xDF4A)
    if test_cacert is None:
        raise Exception("Self-test failed (Get CACert)")
    tlvs, raw = parse_tlv(FIRST_DF4C_RESP + FIRST_DF4D_RESP)
    test_cardcert = tlvs.get(0xDF4C)
    if test_cardcert is None:
        raise Exception("Self-test failed (Get CardCert)")
    
    """ Recorded Card transaction """    
    if not verify_signature_of_session(bytes(FIRST_INPUT), bytes(FIRST_SIGNATURE), bytes(test_cardpub), True):
        raise Exception("Self-test failed (Session)")

    """ Process CACert """
    test_cacert = parse_cacert(bytes(test_cacert), True)
    ok, test_capub = verify_cacert(test_cacert, bytes(CALYPSO_PUBKEY_TEST), True)
    if not ok:
        raise Exception("Self-test failed (verify CACert against RootPub, retrieve CAPub)")

    """ Process CardCert """
    test_cardcert = parse_cardcert(bytes(test_cardcert), True)
    ok, test_cardpub_prime = verify_cardcert(test_cardcert, test_capub, True)
    if not ok:
        raise Exception("Self-test failed (verify CardCert against CAPub, retrieve CardPub)")   
    if not bytes(test_cardpub) == test_cardpub_prime:
        raise Exception("Retrieved CardPub is wrong")
