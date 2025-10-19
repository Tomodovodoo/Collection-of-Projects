from typing import Tuple, Optional, List
import gmpy2

class FSQ:
    def __init__(self):
        self.rs = gmpy2.random_state(0xC0FFEE)
        self.lim = 100000
        self.fbk = 256
        self.scan_soft = 4096
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
        # trial divide by small primes
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
            sR = int(gmpy2.isqrt(R))
            return (ax * sR, ay * sR)
        if (R & 3) == 1 and self.ispp(gmpy2.mpz(R)):
            bx, by = self.two_sq(gmpy2.mpz(R))
            x = ax*bx - ay*by; y = ax*by + ay*bx
            return (abs(x), abs(y))
        return None

    def tri_phase_soft(self, N: gmpy2.mpz, s: int) -> Tuple[int, int, int, int] | None:
        m = int(N)
        rt = int(gmpy2.isqrt(N))
        def bad(r: int) -> bool:
            if r < 0: return True
            if (r & 3) == 3: return True
            if r == 0: return False
            for p in self.P3S:
                if r % p == 0 and (r // p) % p != 0:
                    return True
            return False
        if (m & 7) != 7:
            sv = rt; cnt = self.scan_soft
            while sv >= 0 and cnt:
                r = m - sv*sv
                if not bad(r):
                    ts = self.two_sq_small(r)
                    if ts is not None:
                        a, b = ts; return sv*s, a*s, b*s, 0
                sv -= 1; cnt -= 1
            return None
        sv = rt
        while True:
            r0 = m - sv*sv
            tmp = r0
            while (tmp & 3) == 0: tmp >>= 2
            if (tmp & 7) != 7: break
            sv -= 1
        tv = int(gmpy2.isqrt(r0)); cnt = self.scan_soft
        while tv >= 0 and cnt:
            r = r0 - tv*tv
            if not bad(r):
                ts = self.two_sq_small(r)
                if ts is not None:
                    a, b = ts; return sv*s, tv*s, a*s, b*s
            tv -= 1; cnt -= 1
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
        ts = self.two_sq_small(int(N))
        if ts is not None:
            a, b = ts
            return a * s, b * s, 0, 0
        t = self.tri_phase_soft(N, s)
        if t: return t
        t = self.rand_phase(N, s)
        if t: return t
        t = self.scan_phase(N, s)
        if t: return t
        raise RuntimeError("Somehow it didn't find one. Guess I randomly got a bad number...")

_fsq = FSQ()

def four_squares(n: int) -> Tuple[int, int, int, int]:
    return _fsq.solve(n)
