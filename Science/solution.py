from typing import Tuple
import gmpy2

class FSQ:
    def __init__(self):
        self.rs = gmpy2.random_state(0xC0FFEE)
        self.lim = 100000
        self.fbk = 256

    def rand(self, lo: gmpy2.mpz, hi: gmpy2.mpz) -> gmpy2.mpz:
        if hi <= lo:
            return gmpy2.mpz(lo)
        w = int(hi.bit_length())
        while True:
            r = gmpy2.mpz_urandomb(self.rs, w)
            if r <= (hi - lo):
                return lo + r

    def ispp(self, n: gmpy2.mpz) -> bool:
        return gmpy2.is_prime(n) > 0

    def two_sq(self, p: gmpy2.mpz) -> Tuple[int, int]:
        # Cornacchia
        assert p > 1 and (p & 3) == 1 and self.ispp(p)
        e = (p - 1) // 4
        while True:
            a = self.rand(gmpy2.mpz(2), p - 2)
            t = gmpy2.powmod(a, e, p)
            if (t * t) % p == p - 1:
                break
        r0, r1 = p, t
        while r1 * r1 > p:
            r0, r1 = r1, r0 % r1
        x = int(r1)
        y2 = int(p - r1 * r1)
        y = gmpy2.isqrt(y2)
        if y * y != y2:
            return self.two_sq(p)
        return abs(x), int(y)

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
        r = gmpy2.isqrt(N)
        if r * r == N:
            return int(r * s), 0, 0, 0
        return None

    def rand_phase(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        rtN = gmpy2.isqrt(N)
        for _ in range(self.lim):
            u = self.rand(gmpy2.mpz(0), rtN)
            R = N - u * u
            if R == 0:
                return int(u * s), 0, 0, 0
            rtR = gmpy2.isqrt(R)
            v = self.rand(gmpy2.mpz(0), rtR)
            m = R - v * v
            if m == 0:
                return int(u * s), int(v * s), 0, 0
            if (m & 3) != 1:
                continue
            if self.ispp(m):
                x, y = self.two_sq(m)
                return int(u * s), int(v * s), x * s, y * s
        return None

    def scan_phase(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        rtN = gmpy2.isqrt(N)
        for _ in range(self.fbk):
            u = self.rand(gmpy2.mpz(0), rtN)
            R = N - u * u
            if R <= 0:
                continue
            v = gmpy2.isqrt(R)
            while v >= 0:
                m = R - v * v
                if m == 0:
                    return int(u * s), int(v * s), 0, 0
                if (m & 3) == 1 and self.ispp(m):
                    x, y = self.two_sq(m)
                    return int(u * s), int(v * s), x * s, y * s
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
        t = self.rand_phase(N, s)
        if t: return t
        t = self.scan_phase(N, s)
        if t: return t
        raise RuntimeError("Somehow it didn't find one. Guess I randomly got a bad number...")

_fsq = FSQ()

def four_squares(n: int) -> Tuple[int, int, int, int]:
    return _fsq.solve(n)