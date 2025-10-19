# Huge thanks to https://www.alpertron.com.ar/4SQUARES.HTM for making it possible to understand this problem and how to approach it.
# I naively tried to create 3000 line long compressed mod tables and got 1ms results until 2^250, above which my tables got too big for codewars
# Before that, Hurwitz gaussian peeling which should have the same time complexity, performed exceptionally slow, even for n = 17, so I skipped after trying for a while.
# Read the papers but all my attempts seemed to result in multiple Cornacchia runs and big int divisions which really bogged down the solve time.
# Anyway, this code was made with a few optimizations in mind for n > 2^11500 if needed, but it is not optimal.
# Additionally, big thanks to Bubbler (https://github.com/Bubbler-4) for his solution on codewars, with my solutions drawing on his implemented 1D cache friendly scan

from typing import Tuple, Optional, List
import gmpy2
from gmpy2 import is_prime, isqrt, powmod, jacobi

_SM_SEEDS = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29)
_PFILT    = (3, 5, 7, 11, 13, 17, 19, 23)
_PFILT_PRODUCT = 3*5*7*11*13*17*19*23  # gcd prefilter

class FSQ:
    def __init__(self):
        self.rs = gmpy2.random_state(0xC0FFEE)
        self.lim = 100000
        self.fbk = 256
        self.scan_soft = 4096
        self.big_switch = 11500  # bits: above this, prefer small-prime screen over is_prime (tested numerically)
        # one-time sieve for small primes and a tiny p≡3 (mod 4) set
        limit = 500000
        if limit < 2:
            self.P = []
        else:
            bs = bytearray(b"\x01") * (limit + 1)
            bs[0:2] = b"\x00\x00"
            up = int(limit**0.5)
            for p in range(2, up + 1):
                if bs[p]:
                    start = p * p
                    bs[start:limit + 1:p] = b"\x00" * (((limit - start)//p) + 1)
            self.P = [i for i, v in enumerate(bs) if v]
        self.P3S = [p for p in self.P if p % 4 == 3][:24]

    def rand(self, lo: gmpy2.mpz, hi: gmpy2.mpz) -> gmpy2.mpz:
        if hi <= lo:
            return gmpy2.mpz(lo)
        w = int(hi.bit_length())
        while True:
            r = gmpy2.mpz_urandomb(self.rs, w)
            if r <= (hi - lo):
                return lo + r

    def ispp(self, n: gmpy2.mpz) -> bool:
        return is_prime(n) > 0

    def two_sq(self, p: gmpy2.mpz) -> Tuple[int, int]:
        # Cornacchia
        assert p > 1 and (p & 3) == 1 and self.ispp(p)
        r = None
        for a in _SM_SEEDS:
            if jacobi(a, p) == -1:
                r = powmod(a, (p - 1)//4, p)
                break
        if r is None:
            a = gmpy2.mpz(31)
            while jacobi(a, p) != -1:
                a += 2
            r = powmod(a, (p - 1)//4, p)
        a, b = p, r
        while b*b > p:
            a, b = b, a % b
        s = p - b*b
        if not gmpy2.is_square(s):
            r = p - r
            a, b = p, r
            while b*b > p:
                a, b = b, a % b
            s = p - b*b
        return abs(int(b)), int(isqrt(s))

    def norm(self, N: gmpy2.mpz) -> Tuple[gmpy2.mpz, int]:
        k = 0
        while (N & 3) == 0:
            N >>= 2
            k += 1
        return N, 1 << k

    def prime_case(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        if (N & 3) == 1 and self.ispp(N):
            x, y = self.two_sq(N)
            return x * s, y * s, 0, 0
        return None

    def sq_case(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        r = isqrt(N)
        if r * r == N:
            return int(r * s), 0, 0, 0
        return None

    # fast two-squares for general n
    def two_sq_small(self, n: int) -> Optional[Tuple[int, int]]:
        if n < 0: return None
        if n == 0: return (0, 0)
        if n == 1: return (1, 0)
        nn = int(n)
        e2 = (nn & -nn).bit_length() - 1
        if e2: nn >>= e2
        ax, ay = 1, 0
        if e2:
            rx, ry = 1, 0
            bx, by = 1, 1
            e = e2
            while e:
                if e & 1:
                    x = rx*bx - ry*by; y = rx*by + ry*bx
                    rx, ry = abs(x), abs(y)
                e >>= 1
                if e:
                    x = bx*bx - by*by; y = 2*bx*by
                    bx, by = abs(x), abs(y)
            ax, ay = rx, ry
        for p in self.P[1:]:
            if p * p > nn:
                break
            if nn % p == 0:
                e = 0
                while nn % p == 0:
                    nn //= p; e += 1
                if p % 4 == 3:
                    if e & 1: return None
                    s = pow(p, e // 2)
                    ax *= s; ay *= s
                else:
                    bx, by = self.two_sq(gmpy2.mpz(p))
                    rx, ry = 1, 0; tx, ty = bx, by; ee = e
                    while ee:
                        if ee & 1:
                            x = rx*tx - ry*ty; y = rx*ty + ry*tx
                            rx, ry = abs(x), abs(y)
                        ee >>= 1
                        if ee:
                            x = tx*tx - ty*ty; y = 2*tx*ty
                            tx, ty = abs(x), abs(y)
                    x = ax*rx - ay*ry; y = ax*ry + ay*rx
                    ax, ay = abs(x), abs(y)
        R = int(nn)
        if R == 1:
            return (ax, ay)
        if gmpy2.is_square(R):
            sR = int(isqrt(R))
            return (ax * sR, ay * sR)
        if (R & 3) == 1 and self.ispp(gmpy2.mpz(R)):
            bx, by = self.two_sq(gmpy2.mpz(R))
            x = ax*bx - ay*by; y = ax*by + ay*bx
            return (abs(x), abs(y))
        return None

    # small-bit uses is_prime path; big-bit uses two_sq_small screen.
    def tri_phase_soft(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        m = int(N)
        carry = None
        if (m & 7) == 7:
            t = int(isqrt(N))
            while ((m - t*t) & 7) in (0, 4, 7):
                t -= 1
            carry = t
            m -= t*t

        x = int(isqrt(m))
        nm8 = m & 7
        want_even = nm8 in (1, 2, 5)
        if (x & 1) and want_even: x -= 1
        if (x & 1) == 0 and not want_even: x -= 1

        k = m - x*x
        delta = (x << 2) - 4
        step = 2
        budget = self.scan_soft

        bits = int(gmpy2.num_digits(N, 2))
        big_mode = bits >= self.big_switch
        pfprod = _PFILT_PRODUCT

        while x >= 0 and budget:
            if k == 0:
                return (x*s, 0, 0, 0) if carry is None else (carry*s, x*s, 0, 0)

            even = (k & 1) == 0
            k2 = (k >> 1) if even else k

            if big_mode:
                # Use many small divides first .
                if (k2 & 3) == 1:
                    ts = self.two_sq_small(int(k2))
                    if ts is not None:
                        a, b = ts
                        if even: a, b = abs(a - b), abs(a + b)
                        if carry is None:  return x*s, a*s, b*s, 0
                        else:              return carry*s, x*s, a*s, b*s
            else:
                if (k2 & 3) == 1 and gmpy2.gcd(k2, pfprod) == 1 and is_prime(k2):
                    a, b = self.two_sq(gmpy2.mpz(k2))
                    if even: a, b = abs(a - b), abs(a + b)
                    if carry is None:  return x*s, a*s, b*s, 0
                    else:              return carry*s, x*s, a*s, b*s

            x -= step
            k += delta
            delta -= 8
            budget -= 1

        return None

    def rand_phase(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        rtN = isqrt(N)
        for _ in range(self.lim):
            u = self.rand(gmpy2.mpz(0), rtN)
            R = N - u*u
            if R == 0:
                return int(u*s), 0, 0, 0
            rtR = isqrt(R)
            v = self.rand(gmpy2.mpz(0), rtR)
            m = R - v*v
            if m == 0:
                return int(u*s), int(v*s), 0, 0
            if (m & 3) != 1:
                continue
            if self.ispp(m):
                x, y = self.two_sq(m)
                return int(u*s), int(v*s), x*s, y*s
        return None

    def scan_phase(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        rtN = isqrt(N)
        for _ in range(self.fbk):
            u = self.rand(gmpy2.mpz(0), rtN)
            R = N - u*u
            if R <= 0:
                continue
            v = isqrt(R)
            while v >= 0:
                m = R - v*v
                if m == 0:
                    return int(u*s), int(v*s), 0, 0
                if (m & 3) == 1 and self.ispp(m):
                    x, y = self.two_sq(m)
                    return int(u*s), int(v*s), x*s, y*s
                v -= 1
        return None

    def solve(self, n: int) -> Tuple[int, int, int, int]:
        N = gmpy2.mpz(n)
        if N == 0:
            return 0, 0, 0, 0
        N, s = self.norm(N)
        t = self.sq_case(N, s)
        if t: return t
        t = self.prime_case(N, s)
        if t: return t
        # hybrid fast path
        t = self.tri_phase_soft(N, s)
        if t: return t
        # fallback: two-squares by small primes
        ts = self.two_sq_small(int(N))
        if ts is not None:
            a, b = ts
            return a * s, b * s, 0, 0
        # fallbacks rarely needed
        t = self.rand_phase(N, s)
        if t: return t
        t = self.scan_phase(N, s)
        if t: return t
        raise RuntimeError("Somehow it didn't find one. Guess I randomly got a bad number...")

_fsq = FSQ()

def four_squares(n: int) -> Tuple[int, int, int, int]:
    return _fsq.solve(n)

