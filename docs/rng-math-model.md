# STS2 RNG Correlation Math Model

This note models the correlated RNG problem behind the predictor. It uses raw
`System.Random` samples as the primary variable, because `NextInt` is only a
bucketed view of those samples.

## Constants And Seed Derivation

Let:

$$
M = 2^{31} - 1
$$

and:

$$
Q = 2^{32}
$$

STS2 derives named RNG seeds by 32-bit unsigned addition:

$$
z = B + o \pmod Q
$$

where:

- $B$ is the hidden run or player base seed.
- $o$ is the fixed RNG offset. Named run/player RNGs usually use
  `GetDeterministicHashCode(snake_case(name))`; event RNGs use
  `Owner.NetId + GetDeterministicHashCode(event.Id.Entry)`.
- $z$ is the 32-bit seed passed to `new System.Random((int)z)`.

The .NET compatible `System.Random(int seed)` first folds the signed seed:

$$
S = \operatorname{abs32}(z)
$$

where, ignoring the boundary points for a moment:

$$
\operatorname{abs32}(z) =
\begin{cases}
z, & 0 \le z < M \\
Q-z, & M+3 \le z < Q
\end{cases}
$$

The boundary seeds:

$$
z\in\{M,M+1,M+2\}
$$

are `int.MaxValue`, `int.MinValue`, and `-int.MaxValue`; .NET maps all three to
$S=M$. In the modular formulas below, these boundary cases should be handled as
point exceptions.

The folded seed $S=0$ is not a boundary exception. It has only one unsigned
derived-seed preimage, $z=0$, and is included only in the positive branch.

## Raw Sample Formula

For a fixed call counter $c$, the compatible `System.Random` raw output
`InternalSample()` is affine in the folded seed:

$$
x_c = \alpha_c S + \beta_c \pmod M
$$

The constants $\alpha_c$ and $\beta_c$ depend only on the call counter. The
predictor computes them by evaluating the PRNG at folded seeds 0 and 1:

$$
\beta_c = x_c(0)
$$

$$
\alpha_c = x_c(1) - x_c(0) \pmod M
$$

Since $M$ is prime and $\alpha_c \ne 0$, $\alpha_c$ has a modular inverse.

## `NextInt` As Sample Buckets

`NextInt(n)` maps a raw sample $x \in [0, M)$ into one of $n$ buckets:

$$
\operatorname{NextInt}(n) = \left\lfloor \frac{x n}{M} \right\rfloor
$$

Therefore result $r$ corresponds approximately to the half-open sample bucket:

$$
x \in
\left[
\left\lceil \frac{rM}{n} \right\rceil,
\left\lceil \frac{(r+1)M}{n} \right\rceil
\right)
$$

For exact implementation work, remember that .NET evaluates this through double
arithmetic, so practical code should expand boundaries slightly and verify by
the real `NextInt` formula.

For `NextInt(min, max)`, let $n = max-min$, then:

$$
\operatorname{NextInt}(min,max) = min + \left\lfloor \frac{x n}{M} \right\rfloor
$$

## One Raw Sample To Base Seed Count

For one fixed RNG offset and counter, a raw sample value $x$ determines a
unique folded seed:

$$
S = \alpha_c^{-1}(x-\beta_c) \pmod M
$$

Usually, a folded seed $S$ corresponds to two 32-bit derived seeds:

$$
z = S
$$

and:

$$
z = -S \pmod Q
$$

Then:

$$
B = z - o \pmod Q
$$

So one raw sample normally corresponds to two base seeds. The exception is
$S=0$, which corresponds only to $z=0$. The folded seed $S=M$ is the
`int.MaxValue` / `int.MinValue` / `-int.MaxValue` boundary case and should be
considered separately.

This explains why a wide observation can be huge. `NextInt(4) == 2` covers
roughly $M/4$ raw samples, so it corresponds to roughly:

$$
2 \cdot \frac{M}{4} \approx 1.07 \times 10^9
$$

base seeds.

## Direct Relation Between Two RNG Samples

Instead of recovering base seeds, we can relate two RNGs directly at the raw
sample layer.

Let observed RNG $A$ have offset $o_A$ and counter $c_A$, and target RNG
$B$ have offset $o_B$ and counter $c_B$. Define:

$$
z_A = B + o_A \pmod Q
$$

$$
z_B = B + o_B \pmod Q
$$

and:

$$
\Delta_Q = o_B - o_A \pmod Q
$$

$$
\Delta_M = o_B - o_A \pmod M
$$

Their raw samples are:

$$
x = \alpha_A S_A + \beta_A \pmod M
$$

$$
y = \alpha_B S_B + \beta_B \pmod M
$$

where:

$$
S_A = \operatorname{abs32}(z_A)
$$

$$
S_B = \operatorname{abs32}(z_B)
$$

The absolute-value fold creates at most four sign branches:

$$
(A+,B+),\quad (A+,B-),\quad (A-,B+),\quad (A-,B-)
$$

For branch notation, define:

$$
(r,t) =
\begin{cases}
(+1,0), & + \text{ branch} \\
(-1,2), & - \text{ branch}
\end{cases}
$$

This uses the congruence $Q = 2^{32} \equiv 2 \pmod M$. On a branch:

$$
z_A \equiv r_A S_A + t_A \pmod M
$$

and:

$$
S_B \equiv r_B(z_A + \Delta_M) + t_B \pmod M
$$

Since:

$$
S_A = \alpha_A^{-1}(x-\beta_A) \pmod M
$$

substitution gives a guarded modular line:

$$
y = a x + b \pmod M
$$

where:

$$
k = \alpha_A^{-1} \pmod M
$$

$$
a = \alpha_B r_B r_A k \pmod M
$$

and:

$$
b =
\left[
\beta_B +
\alpha_B
\left(
r_B(t_A + \Delta_M - r_A k \beta_A) + t_B
\right)
\right]
\pmod M
$$

Thus two fixed offset/counter pairs form a union of up to four lines:

$$
y = a_i x + b_i \pmod M
$$

The branches with equal signs have positive slope in this modular sense; the
branches with different signs have negative slope.

## Guard Constraints For A Line

A line is not globally valid for all $x$. It is valid only when the seed
actually lies in the corresponding sign branch.

Given $x$, recover:

$$
S_A = k(x-\beta_A) \pmod M
$$

Then lift $S_A$ into the derived seed for the branch:

$$
z_A =
\begin{cases}
S_A, & A+ \\
Q-S_A, & A-
\end{cases}
$$

and:

$$
z_B = z_A + \Delta_Q \pmod Q
$$

The branch guard requires:

$$
z_A \in H_A
$$

and:

$$
z_B \in H_B
$$

where $H_+$ is the continuous non-boundary non-negative branch and $H_-$
is the continuous non-boundary negative branch:

$$
H_+ = [0, M)
$$

$$
H_- = [M+3, Q)
$$

The omitted boundary points are:

$$
z\in\{M,M+1,M+2\}
$$

The implementation checks them separately.

These guard conditions can be represented in the raw sample coordinate as
modular interval constraints:

$$
(p_i x + q_i)\bmod M \in [L_i, R_i)
$$

Potentially an interval may wrap around modulo $M$, in which case it should be
stored as multiple disjoint half-open intervals.

## Unified Constraint Model

A `NextInt` observation, a branch guard, and a target `NextInt` bucket can all be
expressed in the same form:

$$
(p_i x + q_i)\bmod M \in I_i
$$

where $I_i$ is a set of one or more disjoint intervals in $[0,M)$.

Examples:

Observed result bucket:

$$
(1 \cdot x + 0)\bmod M \in I_{\text{obs}}
$$

Target result bucket for line $y = ax+b$:

$$
(a x + b)\bmod M \in I_{\text{target}}
$$

Branch guard:

$$
(p_{\text{guard}} x + q_{\text{guard}})\bmod M \in I_{\text{branch}}
$$

So a guarded line can be modeled as:

$$
\text{Line}_i =
\left(
y = a_i x + b_i \pmod M,\;
\bigwedge_j
(p_{ij}x + q_{ij})\bmod M \in I_{ij}
\right)
$$

Prediction becomes a counting problem:

$$
\left|\left\{
x \in [0,M):
\forall j,\;
(p_jx+q_j)\bmod M \in I_j
\right\}\right|
$$

For a target `NextInt(k)` distribution, compute this count once per target
bucket and normalize.

## Why Ordinary Intervals Are Not Enough

A single result bucket such as `NextInt(4) == 2` is a contiguous interval in raw
sample space:

$$
x \in I
$$

But mapping it back to base seeds applies:

$$
S = \alpha^{-1}(x-\beta) \pmod M
$$

Multiplication by $\alpha^{-1}$ modulo $M$ turns a contiguous interval of
$x$ values into a modular arithmetic progression over folded seeds. After the
positive/negative seed lift and offset subtraction, those seeds are scattered
through the 32-bit base seed space.

Therefore a plain set of ordinary base-seed intervals would usually fragment
into a huge number of tiny intervals. A better symbolic representation is a
union of guarded modular affine constraints.

## Same-Counter Special Case

The predictor has a high-signal special mode: all observations and the target
must use the same call counter.

If:

$$
c_A = c_B
$$

then:

$$
\alpha_A = \alpha_B = \alpha
$$

and:

$$
\beta_A = \beta_B = \beta
$$

The branch line:

$$
y = a x + b \pmod M
$$

therefore has:

$$
a \in \{+1,-1\}
$$

Same-sign branches become translations:

$$
y = x + b \pmod M
$$

Opposite-sign branches become reflections:

$$
y = -x + b \pmod M
$$

This is much friendlier to `NextInt` buckets. A translation or reflection maps a
sample interval to another interval, possibly split once by modular wraparound.
The different-counter case usually has a large modular multiplier as its slope,
which scatters a sample bucket through the target sample space and weakens the
visible bucket-level relationship.

The same-counter constraint is therefore a useful v1 restriction:

- It captures the strongest cross-stream correlations.
- It keeps the bucket relationship interpretable.
- It avoids the general multi-slope modular counting problem.
- It enables exact conditional prediction by branch enumeration and floor-sum
  counting, without enumerating raw samples.

## Same-Counter Conditional Algorithm

For multiple observations at one shared counter, the fast algorithm chooses one
anchor observation but does not enumerate its samples.

Each non-anchor offset gets a branch state:

$$
(\text{sign}, w),\qquad w\in\{0,1\}
$$

where $w$ records whether:

$$
z_i=z_A+\Delta_Q-wQ
$$

subtracted one copy of $Q$. This wrap bit matters because $Q\equiv2\pmod M$,
so it changes the sample line's constant term by two units in folded-seed space.

For a fixed branch assignment:

1. Convert every integer observation to exact raw sample intervals.
2. Pull every non-anchor observation interval back through a translation or
   reflection $y=\pm x+b\pmod M$.
3. Intersect those ordinary sample intervals in anchor sample space.
4. Convert sign and wrap guards into ordinary intervals for:

   $$
   S_A=\alpha^{-1}(x-\beta)\pmod M
   $$

5. For each target bucket, pull the bucket back to anchor sample space.
6. Count:

   $$
   \left|\{x\in U:\alpha^{-1}(x-\beta)\bmod M\in J\}\right|
   $$

   with a floor-sum prefix count in $O(\log M)$, not by enumerating $x$.
7. Add explicit point checks for the boundary derived seeds
   $z\in\{M,M+1,M+2\}$.

This is exact for supported `NextInt` same-counter calls and its cost depends on
the number of branch assignments and target buckets, not on the width of the
observed `NextInt` bucket.

## Current Predictors

The project currently exposes three conditional predictors:

- `predict_distribution()`: the original explicit base-seed candidate-set
  predictor.
- `predict_same_counter_distribution()`: the same-counter streaming predictor
  used as a simple exact reference implementation.
- `predict_same_counter_fast()`: the non-enumerating same-counter predictor
  described in [same-counter-fast-model.md](same-counter-fast-model.md).

Prefer `predict_same_counter_fast()` when every known call and the target call
use the same counter and all calls are `NextInt`.
