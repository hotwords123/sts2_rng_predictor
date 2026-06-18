# Same-Counter Fast Predictor

这份文档描述 `sts2_rng_predictor.same_counter` 中的快速预测器。它只复用
`rng_compat.py` 里的 STS2 offset、`.NET System.Random(int)` mock 和 raw
sample 仿射系数；它不建立 base seed 候选集合，也不枚举 anchor raw sample。

## Scope

快速预测器只处理所有观测和目标都使用同一个 RNG counter 的情形：

$$
c_{\mathrm{obs},i}=c_{\mathrm{target}}=c
$$

第一版只支持 `NextInt(min,max)` 观测和 `NextInt(min,max)` 目标分布。

这个约束很有用：same counter 时所有 stream 共享同一个 raw sample 仿射式：

$$
x=\alpha S+\beta \pmod M
$$

其中：

$$
M=2^{31}-1,\qquad Q=2^{32}
$$

不同 offset 之间的关系会退化成 sample 空间中的平移或反射，而不是一般的
大斜率模乘。

## Seed Fold

对 hidden base seed $B$ 和 stream offset $o_i$，STS2 传给
`System.Random((int)seed)` 的 32-bit seed 是：

$$
z_i=B+o_i \pmod Q
$$

`.NET Random` 初始化时会先把 signed seed 折叠成非负值。除了边界点外：

$$
S_i=
\begin{cases}
z_i, & z_i\in[0,M) \\
Q-z_i, & z_i\in[M+3,Q)
\end{cases}
$$

边界：

$$
z_i\in\{M,M+1,M+2\}
$$

都折叠到：

$$
S_i=M
$$

这些点不放进区间模型里，而是作为有限个 base seed 点直接检查。

$S_i=0$ 不是边界特例。它只有一个 unsigned derived-seed 原像 $z_i=0$，
并且只属于正分支。

## Exact `NextInt` Buckets

数学上，`NextInt(n)` 近似是：

$$
\left\lfloor \frac{x n}{M}\right\rfloor
$$

所以结果 $r$ 近似对应：

$$
\left[
\left\lceil\frac{rM}{n}\right\rceil,
\left\lceil\frac{(r+1)M}{n}\right\rceil
\right)
$$

实现不直接使用这个公式做边界，因为 .NET 路径经过 double 乘法，边界处可能
差一个 sample。代码使用兼容的 `next_int_from_sample()` 做单调二分，求精确
half-open sample 区间：

$$
I(r)=[L_r,R_r)
$$

结果区间 $[r_0,r_1]$ 对应：

$$
I([r_0,r_1])=[L_{r_0},R_{r_1})
$$

## Branch State

选择一个 anchor stream $A$，它的 offset 是 $o_A$，raw sample 记为
$x$。对另一个 stream $T$，定义：

$$
\Delta_Q=o_T-o_A \pmod Q,\qquad \Delta_M=\Delta_Q \pmod M
$$

`uint32` 加法可能回绕一次。每个非 anchor stream 的分支状态不只是正负号，
还包含 wrap bit：

$$
w_T\in\{0,1\}
$$

并满足：

$$
z_T=z_A+\Delta_Q-w_TQ
$$

这里的 wrap bit 是算法显式枚举的 branch state：它说明从 anchor seed 平移到
目标 seed 时是否跨过了 $Q$ 边界。它会改变这条 branch line 的截距和 guard。
但它不是独立增加一组可见线的自由变量：对一个固定 offset 差和 sign pair，
下面的 guard 通常会把 $w_T$ 限定为唯一值，或让这个 sign/wrap state 为空。
普通散点图里看到的仍然是这些 guarded modular line 的片段。

正负号和 wrap bit 的 guard 是：

$$
\begin{aligned}
w_T=0 &: z_A\in[0,Q-\Delta_Q) \\
w_T=1 &: z_A\in[Q-\Delta_Q,Q)
\end{aligned}
$$

且：

$$
z_T\in H_{s_T}
$$

其中连续区间模型使用：

$$
H_+=[0,M),\qquad H_-=[M+3,Q)
$$

中间省略的 $M,M+1,M+2$ 是 `.NET Random(int)` 的 abs/`int.MinValue`
边界特例；连续区间模型先排除它们，最后由实现单独补回边界点计数。

这两个条件都是 $z_A$ 上的普通区间。再按 anchor 分支转回 $S_A$：

$$
z_A=
\begin{cases}
S_A, & A+ \\
Q-S_A, & A-
\end{cases}
$$

因此每个 branch guard 都能化简成 $S_A$ 空间中的普通 half-open 区间。
多个 stream guard 直接求交即可。

## Same-Counter Line

把 anchor 的 unsigned seed 在模 $M$ 下写成：

$$
z_A\equiv r_A S_A+t_A \pmod M
$$

其中：

$$
(r_A,t_A)=
\begin{cases}
(+1,0), & A+ \\
(-1,2), & A-
\end{cases}
$$

因为：

$$
Q=2^{32}\equiv2\pmod M
$$

带 wrap bit 的 stream seed 是：

$$
z_T\equiv r_AS_A+t_A+\Delta_M-2w_T \pmod M
$$

如果 $T$ 在正分支：

$$
S_T\equiv r_AS_A+t_A+\Delta_M-2w_T \pmod M
$$

如果 $T$ 在负分支：

$$
S_T\equiv -r_AS_A+2-t_A-\Delta_M+2w_T \pmod M
$$

令：

$$
x=\alpha S_A+\beta,\qquad y=\alpha S_T+\beta
$$

于是每个 branch state 给出一条线：

$$
y=\sigma x+b\pmod M,\qquad \sigma\in\{+1,-1\}
$$

当 $S_T=S_A+C$ 时：

$$
y=x+\alpha C\pmod M
$$

当 $S_T=-S_A+C$ 时：

$$
y=-x+\alpha C+2\beta\pmod M
$$

这里的 $C$ 已经包含 $\Delta_M$、anchor sign 常数 $t_A$，以及
wrap 修正 $-2w_T$ 或 $+2w_T$。这就是之前讨论的
`y = a*x + b (mod M)`，但 same-counter 下 $a$ 只可能是 $+1$ 或 $-1$。

## Pulling Observations Back

一个非 anchor 观测给出 target sample 区间 $I_T$。在 branch line 下：

如果：

$$
y=x+b\pmod M
$$

则：

$$
x\in I_T-b\pmod M
$$

如果：

$$
y=-x+b\pmod M
$$

则：

$$
x\in b-I_T\pmod M
$$

平移或反射一个 half-open 区间最多只会因为模 wrap 切成两段。所有观测都拉回
anchor sample 空间后，先求普通区间交集：

$$
U=I_A\cap I_1'\cap I_2'\cap\cdots
$$

目标每个 bucket 也用同样方式拉回，得到 $U_r$。

## Guard Counting

branch guard 已经合并成 $S_A$ 空间里的区间集合 $J$。而：

$$
S_A=\alpha^{-1}(x-\beta)\pmod M
$$

记：

$$
p=\alpha^{-1},\qquad q=-\alpha^{-1}\beta
$$

对某个 target bucket，最终需要计数：

$$
\left|\{x\in U_r:\;(px+q)\bmod M\in J\}\right|
$$

这一步不枚举 $x$。对一个 sample 区间 $[L,R)$ 和一个 guard 区间
$[A,B)$，使用前缀计数：

$$
F(N,T)=\left|\{0\le x<N:\;(px+q)\bmod M<T\}\right|
$$

则：

$$
C([L,R),[A,B))=
[F(R,B)-F(L,B)]-[F(R,A)-F(L,A)]
$$

$F$ 用标准 Euclidean `floor_sum(n,m,a,b)` 在 $O(\log M)$ 内计算。使用
恒等式：

$$
\left|\{x<N:\;(px+q)\bmod M\ge T\}\right|
=
\sum_{x=0}^{N-1}
\left(
\left\lfloor\frac{px+q+M-T}{M}\right\rfloor
-
\left\lfloor\frac{px+q}{M}\right\rfloor
\right)
$$

于是：

$$
F(N,T)=N-\left|\{x<N:\;(px+q)\bmod M\ge T\}\right|
$$

对 interval union 逐段相加即可。

## Algorithm

`predict_same_counter_fast()` 的步骤：

1. 检查所有 observations 和 target 的 `counter` 相同。
2. 把每条 `NextInt` observation 转成精确 raw sample 区间。
3. 选择 sample 区间最窄的 observation 作为 anchor。
4. 枚举每个 offset 的 branch state：正负号和 wrap bit。
5. 把 branch guard 化简到 $S_A$ 区间并求交。
6. 把所有 observation bucket 拉回 anchor sample 空间并求交。
7. 对 target 的每个 `NextInt` bucket，拉回 anchor sample 空间。
8. 用 floor-sum 计数满足 $x$ 区间和 $S_A$ guard 的整数点。
9. 枚举所有涉及 offset 的边界 seed 点：

   $$
   z\in\{M,M+1,M+2\}
   $$

   直接用 RNG mock 检查观测和目标，补入计数。
10. 归一化为目标输出分布。

复杂度主要是：

$$
O(2\cdot4^k \cdot R \cdot \log M)
$$

其中 $k$ 是非 anchor 的不同 offset 数，前面的 2 是 anchor 自身正/负分支，
$R$ 是 target `NextInt` 输出桶数。
它不依赖观测桶宽度，因此可以处理旧枚举器会拒绝的宽 observation。

## Limitations

- 只支持 same-counter。
- 只支持整数 `NextInt` 观测和整数 `NextInt` 目标分布。
- 不自动推断 counter。
- 不整体建模 `Shuffle`、`NextGaussian*` 等组合调用；需要拆成已知 counter 的
  单次底层调用。
