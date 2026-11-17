//! QQ QRC uses a modified DES; standard DES libraries do not decode it.
// Adapted from https://github.com/Mihaly-Ma/karaoke-video-maker/blob/main/backend/kvm/lyrics/qq.py
// MIT License
//
// Copyright (c) 2026 Mihaly Ma
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

use anyhow::{Result, bail};
use std::io::Read;

const SBOX: [[u8; 64]; 8] = [
    [
        14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12,
        11, 9, 5, 3, 8, 4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9,
        1, 7, 5, 11, 3, 14, 10, 0, 6, 13,
    ],
    [
        15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 15, 12, 0, 1,
        10, 6, 9, 11, 5, 0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15,
        4, 2, 11, 6, 7, 12, 0, 5, 14, 9,
    ],
    [
        10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5,
        14, 12, 11, 15, 1, 13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6,
        9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12,
    ],
    [
        7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2,
        12, 1, 10, 14, 9, 10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10,
        10, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14,
    ],
    [
        2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15,
        10, 3, 9, 8, 6, 4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14,
        2, 13, 6, 15, 0, 9, 10, 4, 5, 3,
    ],
    [
        12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13,
        14, 0, 11, 3, 8, 9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5,
        15, 10, 11, 14, 1, 7, 6, 0, 8, 13,
    ],
    [
        4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5,
        12, 2, 15, 8, 6, 1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4,
        10, 7, 9, 5, 0, 15, 14, 2, 3, 12,
    ],
    [
        13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6,
        11, 0, 14, 9, 2, 7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10,
        8, 13, 15, 12, 9, 0, 3, 5, 6, 11,
    ],
];
const KEY_PERM_C: [u8; 28] = [
    56, 48, 40, 32, 24, 16, 8, 0, 57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59,
    51, 43, 35,
];
const KEY_PERM_D: [u8; 28] = [
    62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13, 5, 60, 52, 44, 36, 28, 20, 12, 4,
    27, 19, 11, 3,
];
const KEY_COMPRESSION: [u8; 48] = [
    13, 16, 10, 23, 0, 4, 2, 27, 14, 5, 20, 9, 22, 18, 11, 3, 25, 7, 15, 6, 26, 19, 12, 1, 40, 51,
    30, 36, 46, 54, 29, 39, 50, 44, 32, 47, 43, 48, 38, 55, 33, 52, 45, 41, 49, 35, 28, 31,
];
const KEY_RND_SHIFT: [u8; 16] = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1];
const IP_L: [u8; 32] = [
    57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3, 61, 53, 45, 37, 29, 21, 13, 5, 63,
    55, 47, 39, 31, 23, 15, 7,
];
const IP_R: [u8; 32] = [
    56, 48, 40, 32, 24, 16, 8, 0, 58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62,
    54, 46, 38, 30, 22, 14, 6,
];
const P_PERM: [(u8, u8); 32] = [
    (15, 0),
    (6, 1),
    (19, 2),
    (20, 3),
    (28, 4),
    (11, 5),
    (27, 6),
    (16, 7),
    (0, 8),
    (14, 9),
    (22, 10),
    (25, 11),
    (4, 12),
    (17, 13),
    (30, 14),
    (9, 15),
    (1, 16),
    (7, 17),
    (23, 18),
    (13, 19),
    (31, 20),
    (26, 21),
    (2, 22),
    (8, 23),
    (18, 24),
    (12, 25),
    (29, 26),
    (5, 27),
    (21, 28),
    (10, 29),
    (3, 30),
    (24, 31),
];
const _INVIP_BYTE_ORDER: [u8; 8] = [3, 2, 1, 0, 7, 6, 5, 4];

fn bitnum(buf: &[u8], b: u8, c: u8) -> u32 {
    let idx = usize::from((b / 32) * 4 + 3 - (b % 32) / 8);
    u32::from((buf[idx] >> (7 - (b % 8))) & 1) << c
}
fn bit_r(a: u32, b: u8, c: u8) -> u32 {
    ((a >> (31 - b)) & 1) << c
}
fn schedule(key: &[u8], decrypt: bool) -> [[u8; 6]; 16] {
    let mut out = [[0; 6]; 16];
    let (mut c, mut d) = (0u32, 0u32);
    for i in 0..28 {
        c |= bitnum(key, KEY_PERM_C[i], 31 - i as u8);
        d |= bitnum(key, KEY_PERM_D[i], 31 - i as u8);
    }
    for (i, shift) in KEY_RND_SHIFT.iter().enumerate() {
        c = ((c << shift) | (c >> (28 - shift))) & 0xfffffff0;
        d = ((d << shift) | (d >> (28 - shift))) & 0xfffffff0;
        let rk = &mut out[if decrypt { 15 - i } else { i }];
        for j in 0..24 {
            rk[j >> 3] |= bit_r(c, KEY_COMPRESSION[j], 7 - (j & 7) as u8) as u8;
        }
        // This modified key schedule subtracts 27, unlike standard DES.
        for j in 24..48 {
            rk[j >> 3] |= bit_r(d, KEY_COMPRESSION[j] - 27, 7 - (j & 7) as u8) as u8;
        }
    }
    out
}
fn f(state: u32, key: &[u8; 6]) -> u32 {
    const E: [u8; 48] = [
        32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17, 16, 17,
        18, 19, 20, 21, 20, 21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1,
    ];
    let mut expanded = 0u64;
    for p in E {
        expanded = (expanded << 1) | u64::from((state >> (32 - p)) & 1);
    }
    let mut s = 0;
    for (i, sbox) in SBOX.iter().enumerate() {
        let six = ((expanded >> (42 - 6 * i)) & 63) as u8;
        let key_bits =
            ((u64::from_be_bytes([0, 0, key[0], key[1], key[2], key[3], key[4], key[5]])
                >> (42 - 6 * i))
                & 63) as u8;
        let a = six ^ key_bits;
        let index = (a & 0x20) | ((a & 0x1f) >> 1) | ((a & 1) << 4);
        s |= u32::from(sbox[usize::from(index)]) << (28 - 4 * i);
    }
    let mut out = 0;
    for (b, c) in P_PERM {
        out |= bit_r(s, b, 31 - c);
    }
    out
}
fn block(buf: &[u8], keys: &[[u8; 6]; 16]) -> [u8; 8] {
    let (mut s0, mut s1) = (0, 0);
    for k in 0..32 {
        s0 |= bitnum(buf, IP_L[k], 31 - k as u8);
        s1 |= bitnum(buf, IP_R[k], 31 - k as u8);
    }
    for key in &keys[..15] {
        let t = s1;
        s1 = f(s1, key) ^ s0;
        s0 = t;
    }
    s0 ^= f(s1, &keys[15]);
    let mut out = [0; 8];
    for k in 0..8 {
        let base = 7 - k as u8;
        let mut v = 0;
        for t in 0..4 {
            v |= bit_r(s1, base + 8 * t, 7 - 2 * t);
            v |= bit_r(s0, base + 8 * t, 6 - 2 * t);
        }
        out[usize::from(_INVIP_BYTE_ORDER[k])] = v as u8;
    }
    out
}
pub(super) fn decode(hex: &str) -> Result<String> {
    let hex = hex.trim();
    if hex.is_empty() || hex.len() > 2_097_152 || !hex.len().is_multiple_of(16) || !hex.is_ascii() {
        bail!("invalid QRC ciphertext size");
    }
    let mut data = Vec::with_capacity(hex.len() / 2);
    for pair in hex.as_bytes().as_chunks::<2>().0 {
        let value = std::str::from_utf8(pair)?;
        data.push(
            u8::from_str_radix(value, 16).map_err(|_| anyhow::anyhow!("invalid QRC ciphertext"))?,
        );
    }
    const KEY: &[u8] = b"!@#)(*$%123ZXC!@!@#)(NHL";
    let keys = [
        schedule(&KEY[16..24], true),
        schedule(&KEY[8..16], false),
        schedule(&KEY[..8], true),
    ];
    let mut plain = Vec::with_capacity(data.len());
    for input in data.as_chunks::<8>().0 {
        let mut b = *input;
        for k in &keys {
            b = block(&b, k);
        }
        plain.extend_from_slice(&b);
    }
    let mut out = Vec::new();
    flate2::read::ZlibDecoder::new(plain.as_slice())
        .take(1_048_577)
        .read_to_end(&mut out)?;
    if out.len() > 1_048_576 {
        bail!("QRC expands beyond 1 MiB");
    }
    Ok(String::from_utf8(out)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn decodes_modified_des_and_rejects_bad_input() {
        assert_eq!(
            decode("f0263c4f295890d8f78aa4312cf7f0f882dcfd8b28b7e49879fdc8e3b487e44c").unwrap(),
            "QRC decoder fixture"
        );
        for bad in [
            "",
            "0",
            "gggggggggggggggg",
            "0000000000000000",
            "😀000000000000",
        ] {
            assert!(decode(bad).is_err());
        }
    }
}
