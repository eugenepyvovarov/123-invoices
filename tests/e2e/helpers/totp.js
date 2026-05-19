const crypto = require('crypto');

const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

function decodeBase32(secret) {
  let bits = '';

  for (const character of secret.replace(/=+$/g, '').toUpperCase()) {
    const value = BASE32_ALPHABET.indexOf(character);
    if (value === -1) {
      throw new Error(`Invalid base32 character: ${character}`);
    }
    bits += value.toString(2).padStart(5, '0');
  }

  const bytes = [];
  for (let offset = 0; offset + 8 <= bits.length; offset += 8) {
    bytes.push(parseInt(bits.slice(offset, offset + 8), 2));
  }

  return Buffer.from(bytes);
}

function hotp(secret, counter, digits = 6) {
  const key = decodeBase32(secret);
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));

  const hmac = crypto.createHmac('sha1', key).update(counterBuffer).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const code =
    ((hmac[offset] & 0x7f) << 24)
    | ((hmac[offset + 1] & 0xff) << 16)
    | ((hmac[offset + 2] & 0xff) << 8)
    | (hmac[offset + 3] & 0xff);

  return String(code % (10 ** digits)).padStart(digits, '0');
}

function totp(secret, options = {}) {
  const step = options.step || 30;
  const epochMs = options.now || Date.now();
  return hotp(secret, Math.floor(epochMs / 1000 / step), options.digits || 6);
}

module.exports = {
  totp,
};
