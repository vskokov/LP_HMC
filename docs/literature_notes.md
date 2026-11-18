# Literature notes: Lifshitz / Brazovskii / moat physics for the LP_HMC paper

Model: 3D lattice real scalar, `H = Σ_x [ Z/2 (∇φ)² + 1/2 (∇²φ)² + m²/2 φ² + λ/4 φ⁴ ]`,
λ = 4, T = 1, Z₂ symmetry. Mean field: isotropic Lifshitz point (LP) at Z = 0, m² = 0;
uniform order for Z > 0, modulated order with `q*² = -Z/2` for Z < 0.

All keys refer to `paper/refs.bib` (92 entries). Each entry was checked against Crossref by
DOI; arXiv ids were taken from INSPIRE-HEP or the arXiv API. "Abstract-verified" means the
quoted statement was read from the paper's abstract (INSPIRE, Crossref, APS abstract page or
arXiv) during this survey. "Full text checked" means the PDF was read. Statements marked
**[standard]** are textbook results I did not re-read in the cited source. Statements marked
**[our derivation]** are short calculations done for these notes and should be checked before
they appear in the paper.

Binder-cumulant convention used throughout: `U4 = 1 - <M⁴>/(3<M²>²)`.

---

## 1. Lifshitz points

- **Hornreich1975**: Hornreich, Luban, Shtrikman, PRL 35, 1678. The original paper. It defines
  the LP as a multicritical point on the λ line that separates ordered phases with k = 0 and k ≠ 0.
  For isotropic systems two exponents are enough; it uses an ε-type expansion (abstract-verified).
- **Hornreich1975b** (O(1/n) exponents) and **Hornreich1977** (an exactly solvable spherical-type
  model with a multicritical point) are early large-n and exact results.
- **Hornreich1980**: J. Magn. Magn. Mater. review of phase diagrams and critical behaviour at the LP.
  Only the metadata was verified.
- **Michelson1977**: Landau theory near a uniaxial LP. The ferro (II) ↔ sinusoidal (III) line is
  **first order** (latent heat, metastability) and is **tangent** to the order–disorder line at the
  LP (abstract-verified). This is the mean-field baseline for our uniform ↔ modulated boundary.
- **Erzan1977**: scaling of the spherical model and other Ornstein–Zernike systems near an
  *isotropic* LP for 2 < d < 4. It offers "a different interpretation of the Lifshitz point" and
  discusses an LP at zero temperature (abstract-verified). It does **not** say that the isotropic
  LP exists at finite T in d = 3. In the large-n / OZ picture, the isotropic LP in d < 4 is pushed
  to T = 0.
- **Sak1978** (ε = 5 − d for biaxial m = 2) and **Grest1978** (low-temperature RG "above the lower
  critical dimensionality", with ε = d − 2.5 for the uniaxial m = 1 case) are abstract-verified.
  Grest1978 places the lower critical dimension of the uniaxial LP at d_L = 2.5. That is the
  m-axial formula d_L = 2 + m/2.
- **Diehl2002** (Acta Phys. Slovaca review; full text checked), **Diehl2000**, **Shpot2001**,
  **Diehl2002b** (isotropic LP to O(ε₈²)), **Shpot2005**, **Shpot2012** (large n). These are
  two-loop field theory for m-axial LPs. Quotable facts from Diehl2002:
  - The upper critical dimension is `d*(m) = 4 + m/2`, so the **isotropic LP (m = d) has d* = 8**
    and is expanded in ε₈ = 8 − d.
  - For continuous O(n) symmetry, the ordered phase is unstable for `d ≤ 2 + m/2`. For the
    isotropic case this gives **d_L = 4**. This is the origin of the statement that "the isotropic
    LP has lower critical dimension 4."
  - The modulated phase near an LP behaves like a 2n-component model. Orientational LRO of a helical
    phase is absent for m ≤ d ≤ m + 1. This includes the isotropic case d = m. Diehl states it for
    the helical, n ≥ 2 case.
  - Caveat: the "d_L = 4" argument is a spin-wave argument for n ≥ 2. For n = 1 (our case) the
    corresponding statement concerns the stability of the modulated phase (see Section 3) and the
    Brazovskii mechanism (Section 2). It is not a Goldstone-mode theorem.
- **Selke1988**: Phys. Rep. review of the ANNNI model, the paradigm uniaxial (m = 1) LP. Only the
  metadata was verified.
- **Pleimling2001**: Monte Carlo of the 3D ANNNI model at its *uniaxial* LP, with anisotropic
  scaling. It shows that uniaxial LPs survive in d = 3. This is the contrast case to our isotropic
  model.

## 2. Brazovskii fluctuation-induced first-order transition

- **Brazovskii1975**: for an isotropic system whose soft modes lie on a sphere |q| = q₀, the
  shell's phase space makes the one-loop (Hartree) correction diverge like 1/√r in d = 3. The
  mean-field second-order transition becomes **first order**. Only the metadata was verified (the
  reprint DOI). **[standard]**
- **Swift1977**: Rayleigh–Bénard convection maps onto a crystallization model with **no cubic
  term**, so mean field gives a second-order transition. Following Brazovskii, fluctuations make it
  discontinuous in 3D (abstract-verified). Our φ⁴ model is in the same no-cubic class.
- **Leibler1980**: mean-field theory of microphase separation in block copolymers. For symmetric
  diblocks (no cubic term) the transition goes directly from disorder to lamellae at a
  second-order mean-field point. **[standard]**
- **Fredrickson1987**: maps the diblock Hamiltonian onto the Brazovskii form. Symmetric diblocks
  undergo a **first-order** transition at `(χN)_t = 10.495 + 41.022 N^{-1/3}`, with a
  peak-scattering maximum of `0.12328 N^{1/3}`. Windows of composition open into lamellar,
  hexagonal and bcc phases (abstract-verified). The fluctuation parameter is N̄^{-1/3}: the jump
  vanishes as N → ∞, which is the mean-field limit.
- **Bates1988**: SANS experiment showing non-mean-field behaviour above the "weakly first-order
  microphase-separation transition." It is quantitatively explained by Brazovskii–Hartree theory
  (abstract-verified). **Bates1990** is the Annual Review of block-copolymer theory and experiment.
- **Hohenberg1995**: nucleation of lamellae in a Brazovskii transition. The mean-field theory has
  **no phase coexistence**, so a self-consistent coarse-graining (momentum-shell RG for the
  Brazovskii class) is needed. The critical droplet is **anisotropic** (abstract-verified).
- **Kats1993**: Phys. Rep. "Weak crystallization theory." It reviews which structures (lamellar,
  hexagonal, bcc, ...) win near a Brazovskii-type transition. Only the metadata was verified.
  **[standard]** expectation for why the lamellar phase wins in our model: without a cubic
  invariant (Z₂ symmetry), the triangle (three-wave) couplings that stabilize hexagonal and bcc
  phases are absent. The one-mode (lamellar) state then minimizes the quartic Landau energy. This
  matches Leibler1980 and Fredrickson1987 at symmetric composition (f = 1/2, lamellar).
- **Barbosa1993**: isotropic competing interactions on a cubic lattice in a field, studied with an
  ε expansion. The paramagnetic → modulated transition **stays first order** at small field and
  turns continuous at a **tricritical point** at larger field. Varying q_c gives a line of
  tricritical points that "must end at a Lifshitz tricritical point at q_c = 0" (abstract-verified).
- **Barci2007**: 2D Ising-symmetric competing interactions, Hartree RG. A repulsive quadrupole
  interaction gives a first-order transition to stripes "in agreement with the well-known
  Brazovskii result." An attractive one gives a continuous isotropic–nematic transition
  (abstract-verified). An intermediate nematic phase is a possible alternative to direct lamellar
  order.
- **Fredrickson1989**: kinetics of metastable states in block-copolymer melts (Brazovskii class).
  Only the metadata was verified.

**Strength versus q*** **[our derivation, needs checking]**: near the shell,
`ε(q) = r + (q² − q*²)² ≈ r + 4q*²(q − q*)²`. The Hartree loop is then
`∫d³q/(2π)³ 1/ε(q) ≈ q*/(4π√r)`, i.e. ∝ q*/√r. So Brazovskii fluctuations are **weaker for
small q*** at fixed r, but they apply only while √r ≪ q*². When q*² ≲ √r the shell is not
resolved and the system crosses over to isotropic-LP (q⁴) scaling. In bare couplings,
`Z = -2q*²` gives a fluctuation strength ∝ √|Z|, applicable when r ≪ Z²/4. The first-order jump
therefore weakens toward the LP. On a lattice, it also gets harder to resolve because q* → 2π/L.

## 3. Lamellar / smectic fluctuations (LRO vs QLRO)

- **Chaikin1995** (textbook; DOI 10.1017/CBO9780511813467) **[standard]**: smectic-A elasticity
  `F = ½∫[B(∂_z u)² + K(∇⊥²u)²]`. Layer displacements have `<u²> ∝ (T/√(BK)) ln L` in 3D. This is
  the Landau–Peierls instability: no true 1D density-wave LRO. Bragg peaks become power laws
  `S(q) ∝ |q_z − q₀|^{-2+η}` with the **Caillé exponent** `η = q₀² k_BT/(8π√(BK))`. The Caillé
  original (C. R. Acad. Sci. B 274, 891 (1972)) has no DOI and is cited in Grinstein1981's
  reference list. See "Unverified leads" below.
- **Grinstein1981, Grinstein1982**: anharmonic RG in 3D. B vanishes and K diverges
  logarithmically at small wavevector. Correlations decay as `r^{-x}` with
  `x = η(T)(ln r)^{η̃}`, `η̃ = 1/5` universal (abstract-verified). The 3D smectic is therefore
  only marginally QLRO, with log-corrected power laws.
- **Toner1981**: in 2D, layer fluctuations and dislocations destroy smectic order at any T > 0 and
  give a nematic-like phase (abstract-verified). This is relevant only as a dimensional contrast.
- **Golubovic1994**: smectic-A ↔ KPZ mapping and anomalous elasticity. Only relevant if
  head-to-tail asymmetry is present. Our Z₂ (φ → −φ) model has none.
- QCD analogues (Section 5): **Hidaka2015**, **Lee2015**, **Pisarski2019**, **Pisarski2020**.

**Applicability to our model** **[our derivation]**: a lamellar state `φ ≈ A cos(q*·x + q* u)`
in a rotation-invariant continuum theory has a soft displacement mode. The compression modulus B
comes from the (q² − q*²)² curvature along the layer normal. The transverse term is purely K∇⊥⁴u,
because rotations of the layer normal cost nothing, so no (∇⊥u)² term appears. This is exactly
smectic-A elasticity, and it gives the Landau–Peierls log divergence in d = 3. On the **cubic
lattice** the rotational symmetry is only cubic. Orientations along lattice axes are pinned and a
small (∇⊥u)² term should appear, which restores true LRO at the largest scales. We expect this
lattice-anisotropy pinning to be weak when q*a ≪ 1, so our finite volumes are likely in the
smectic (log) regime.

## 4. Non-perturbative / RG / large-N results on isotropic LPs and the 3D fate

- **Bonanno2015** (FRG, single component, isotropic LP, proper-time regulator): Lifshitz fixed
  points are found **only for 5.5 < d < 8** (abstract-verified). This is the strongest
  non-perturbative statement that **no isotropic Ising-LP fixed point exists in d = 3**.
- **Zappala2017**: O(N) at large N, LPA′. A non-trivial (tricritical) isotropic LP exists for
  **4 < d < 8**, and η_N vanishes at d = 4 and d = 8 (abstract-verified).
- **Zappala2018**: U(1) at the "conjectured lower critical dimension d = 4." It finds a line of
  Lifshitz points with BKT-like features (abstract-verified). This supports **d_L = 4** for the
  isotropic LP.
- **Bervillier2004** (exact RG equation for the LP) and **Essafi2012** (NPRG for m-axial LP with
  N = 3 in d = 3, reliable for *anisotropic* m) are background. Neither establishes an isotropic
  LP in d = 3.
- Polymer theory and experiment, the best-established "LP destroyed in 3D" evidence:
  - **Bates1995**: in an A/B/A–B blend, mean-field Lifshitz exponents (γ = 1, ν = 1/4) were seen
    in the disordered phase within ~1 K of the transition (abstract-verified).
  - **Bates1997**: near the mean-field isotropic LP a **bicontinuous microemulsion** forms. It is
    attributed to fluctuations (abstract-verified).
  - **Kielhorn1997**: one-loop self-consistent theory. All mean-field second-order microphase
    transitions become **first order**. "As a consequence, the MFT Lifshitz critical point is
    destroyed" (abstract-verified).
  - **Duchs2003**: field-theoretic Monte Carlo of the ternary blend. The ODT shifts, and there are
    "strong signatures" of a microemulsion near the mean-field LP (abstract-verified).
  - **Schwahn2000**: SANS on fluctuations near the isotropic Lifshitz critical point. Only the
    metadata was verified.
- **Pisarski2020**: O(N) with N = 2. Chiral spirals produce static transverse modes with double
  poles and linear IR divergences in any d, which disorder the condensate. A "quantum spin
  liquid"-like regime appears (exponential × oscillatory correlators), established at large N and
  conjectured for N > 2 (abstract-verified). This applies to N ≥ 2, **not** directly to N = 1.

## 5. QCD context: moat regimes and inhomogeneous chiral phases

- **Pisarski2019** (PRD 99 074025): pion/kaon condensates and chiral spirals show QLRO "analogous
  to smectic liquid crystals." There is a continuous line of **first-order** transitions between
  inhomogeneous and homogeneous phases. "While mean field theory predicts … a Lifshitz point …,
  in three spatial dimensions strong infrared fluctuations wash out any Lifshitz point." In its
  place is a **Lifshitz regime** with quartic-dominated propagators (abstract-verified). This is
  our working hypothesis, stated for QCD.
- **Pisarski2019b** (Universe 5, 48; the published title is "A Pedagogical Introduction to the
  Lifshitz Regime", **not** "A pion liquid in higher dimensions"): fluctuations about the LP
  "significantly alter the phase diagram." It draws the analogy to the polymer bicontinuous
  microemulsion (abstract-verified).
- **Pisarski2021b**: FRG suggests the Lifshitz regime is wide in (T, μ_B). The CEP critical region
  is small, attributed to the narrowness of the tricritical region (abstract-verified).
- **Pisarski2021** (PRL): a moat spectrum makes particle numbers and correlations peak at nonzero
  momentum (abstract-verified). **Rennecke2023**: HBT/interferometry in a moat regime.
- **Fu2020**: QCD FRG. CEP at (T, μ_B) = (107, 635) MeV, with indications of an inhomogeneous
  (moat) regime for μ_B ≳ 417 MeV (abstract-verified). **Fu2025**: the moat comes from
  particle–hole fluctuations at the Fermi surface ("moaton" quasiparticle). An inhomogeneous
  instability is "highly unlikely for μ_B ≤ 630 MeV" (abstract-verified).
- **Haensch2024**: mixing of condensate, density and Polyakov loops makes the Hessian
  non-Hermitian, with complex-conjugate eigenvalues signalling modulated correlations
  (abstract-verified). **Rennecke2026** (Rennecke–Yin, PRD 113, 074015): the extent of the moat
  regime in the quark-meson model depends strongly on renormalization and on the quark–meson
  interaction (abstract-verified).
- **Nickel2009** (PRL): in the chiral limit of NJL-type models, the inhomogeneous region generically
  reaches out to the chiral critical point, which becomes a Lifshitz point (abstract-verified).
  **Nickel2009b**: PRD companion paper. **Buballa2015**: the standard review. **Kojo2010**:
  quarkyonic chiral spirals.
- **Hidaka2015**: NJL real-kink-crystal phase. One-dimensional modulation is destroyed by phonon
  fluctuations at T > 0, with anisotropic algebraic decay (QLRO), i.e. Landau–Peierls
  (abstract-verified). **Lee2015**: the dual chiral density wave likewise loses LRO but keeps QLRO,
  "as in liquid crystals" (abstract-verified).
- Model and lattice studies:
  - **Koenigstein2022**: the bosonic two-point function detects inhomogeneous instabilities in the
    1+1D GN model.
  - **Lenz2020**: 1+1D GN on the lattice at finite N_f.
  - **Buballa2021**: strong regulator dependence in the 2+1D GN model.
  - **Pannullo2023**: no inhomogeneous phase and **no moat regime** in a broad class of 2+1D
    four-fermion/Yukawa models (abstract-verified).
  - **Pannullo2024**: strong scheme dependence in NJL.
- **Winstel2024** (Acta Phys. Pol. B Proc. Suppl. 17, 6-A22): **HMC lattice simulation of a scalar
  O(N) model with negative bare wave-function renormalization**. "Bosonic quantum fluctuations
  disorder the inhomogeneous condensate," which yields a "Quantum Pion Liquid" with spatially
  oscillating, exponentially decaying correlators (abstract-verified). **This is the closest prior
  lattice study to ours.** It is O(N) (N ≥ 2 by implication), so Goldstone/Mermin–Wagner-type
  disordering is available. For our N = 1 model those mechanisms are absent.
- **Schindler2020**: lattice simulation of a PT-symmetric scalar theory showing pattern formation
  in the critical region, interpreted as arrested spinodal decomposition. It finds no distinct
  microphases (abstract-verified).

## 6. Finite-size diagnostics

- **Binder1981**: introduces the cumulant. Only the metadata was verified. **[standard]**
  U4 → 2/3 deep in a single ordered phase and → 0 for a Gaussian disordered phase.
- **3D Ising fixed point (Hasenbusch2010; full text checked)**: `U4* ≡ <m⁴>/<m²>² = 1.6036(1)`
  (Table V; fit value 1.60357(1)). In our convention this is **U4* = 1 − 1.6036/3 = 0.46547(3)**.
  The same paper gives ν = 0.63002(10), η = 0.03627(10), ω = 0.832(6) (abstract-verified).
  **Ferrenberg2018**: ν = 0.629912(86), K_c = 0.221654626(5) (abstract-verified).
- **Mean-field U4 values** **[our derivation, checked numerically]**. For a single-mode
  distribution `P(M) ∝ exp(−M^k)`:
  - Ising φ⁴ (k = 4, d ≥ 4): U4 = 1 − Γ(1/4)Γ(5/4)/(3Γ(3/4)²) = **0.2705**.
  - Tricritical φ⁶ (k = 6): `<M⁴>/<M²>² = Γ(5/6)Γ(1/6)/Γ(1/2)² = 2`, so **U4 = 1/3**.
  - d = 3 is the **upper critical dimension of the tricritical point** (**Riedel1972** is the
    tricritical-scaling reference; **Deng2004** states "3 is the upper tricritical dimensionality
    of Ising systems," abstract-verified). The 3D tricritical U4 should therefore approach the
    φ⁶ mean-field value, up to logarithmic corrections. Deng2004 computes the exact mean-field
    tricritical Blume–Capel Binder ratio. For simulations that conserve vacancies, the constrained
    (Fisher-renormalized) tricritical point has a **different** Binder ratio, and the 3D data do
    not match the mean-field prediction. Our HMC at fixed (Z, m²) is unconstrained, grand-canonical
    in φ², so the unconstrained value is the relevant one. Check the numerical value in the full
    text before quoting it.
  - Three-peak first-order coexistence (peaks at 0 and ±M₀ with weights w, (1−w)/2, (1−w)/2):
    `U4 = 1 − 1/(3(1−w))`. This gives U4 = 0.5 for equal weights and becomes **negative** for
    w > 2/3. That is the origin of the first-order Binder dip.
- **First-order finite-size scaling**:
  - **Binder1984**: thermodynamic fluctuation theory; jump magnitudes from FSS
    (abstract-verified).
  - **Challa1986**: double-Gaussian energy distribution. Specific-heat peak height ∝ L^d and shift
    ∝ L^{-d} (abstract-verified for the double-Gaussian approach; the L^d scalings are
    **[standard]**).
  - **Lee1991**: the energy Binder cumulant has a minimum
    `2/3 − (e₁/e₂ − e₂/e₁)²/12 + O(L^{-d})` at `T_c(L) − T_c = O(L^{-d})` (abstract-verified).
  - **Lee1990**: the free-energy barrier `ΔF(L) = ln(P_max/P_min)` grows ∝ L^{d−1} (interfacial
    cost) at a first-order transition and is L-independent at a continuous one. The
    L^{d−1} statement is **[standard]**; the abstract only says the method identifies weak
    first-order transitions "even when … L/ξ" is small.
  - **Borgs1990**: rigorous FSS at first-order transitions. **Janke1993**: transition points
    without power-law corrections.
  - **Vollmayr1993**: phenomenological theory of the *order-parameter* distribution at
    thermally driven first-order transitions. The magnetization Binder cumulant has a negative
    minimum whose depth grows ∝ L^d. That scaling is **[standard]**; the abstract was not
    retrievable (closed Springer).
  - Susceptibility peak at a first-order transition: `χ_max ∝ L^d` **[standard]**. At a 3D Ising
    point: `χ_max ∝ L^{γ/ν} = L^{2−η} ≈ L^{1.964}`, from Hasenbusch2010's η.
- **Critical endpoint (CEP) theory**:
  - **Fisher1990**: at a CEP, a critical phase coexists with a noncritical spectator phase α. New
    singularities appear in the α phase boundary and in surface tensions, and universal amplitude
    ratios exist (abstract-verified).
  - **Fisher1991**: phase-boundary singularities near CEPs (abstract-verified).
  - **Wilding1997**: grand-canonical MC of a symmetric binary LJ mixture. Confirms a singular
    coexistence diameter and the Fisher–Upton chemical-potential singularity at a CEP
    (abstract-verified).
  - **Wilding1996**: tricritical order-parameter distribution matching in a 2D spin fluid. It is
    the methodological template for identifying a tricritical point from P(M).
  - **Zierenberg2015**: multicanonical 3D Blume–Capel through first- and second-order regimes and
    near the tricritical point (abstract-verified).

## 7. Methods

- **Duane1987**: HMC.
- **Torrie1977**: umbrella sampling.
- **Swendsen1986**: replica MC.
- **Hukushima1996**: exchange MC (parallel tempering).
- **Sugita2000**: multidimensional/Hamiltonian replica exchange.
- **Ferrenberg1988** and **Ferrenberg1989**: single- and multiple-histogram reweighting.
- **Kumar1992**: WHAM.
- **Shirts2008**: MBAR.
- **Berg1992**: multicanonical sampling. Tunnelling time grows only ∝ L^{2.65} for the 2D 10-state
  Potts model, versus exponentially for heat-bath (abstract-verified).

All of the above have verified metadata.

## 8. Prior Monte Carlo of Brazovskii / Lifshitz / higher-derivative scalars

- **Pleimling2001**: 3D ANNNI at its uniaxial LP.
- **Fredrickson1989**: block-copolymer metastability, with Binder as co-author.
- **Duchs2003**: field-theoretic MC of a ternary blend near the isotropic LP.
- **Winstel2024**: HMC of an O(N) moat scalar.
- **Schindler2020**: PT-symmetric scalar, pattern formation.
- I found **no prior lattice study of the N = 1 isotropic (∇²φ)² φ⁴ theory that maps the
  uniform-line termination near the LP**. Searches covered arXiv and INSPIRE ("Lifshitz point" +
  lattice/Monte Carlo; "moat" + lattice; citations of Pisarski2019 and Winstel2024). This
  suggests our study fills a real gap. Absence of evidence is not proof; see the leads below.

---

## Synthesis: what theory predicts for our model

**(a) Fate of the isotropic LP in d = 3.**
- *Established (field theory):* the isotropic LP has upper critical dimension 8 (Diehl2002).
- *Supported but not rigorous:* the lower critical dimension is 4. The spin-wave argument is
  rigorous only for O(n ≥ 2) (Diehl2002), and Zappala2018 calls d = 4 "conjectured."
- *Non-perturbative support for "no LP in d = 3":* FRG finds isotropic Ising Lifshitz fixed points
  only for 5.5 < d < 8 (Bonanno2015), and O(N→∞) ones only for 4 < d < 8 (Zappala2017).
- *Experimental and simulation support:* the polymer Lifshitz point is destroyed and replaced by a
  microemulsion channel and first-order lines (Kielhorn1997, Bates1997, Duchs2003).
- *Same claim in QCD:* Pisarski2019 and Pisarski2019b.
- *Consistency with our data:* termination of the Ising line at Z* ≈ −0.956, shifted away from
  the mean-field Z = 0, is consistent with all of this. **Not established:** exactly what replaces
  the LP for N = 1 in d = 3. The literature favours first-order lines plus a disordered
  "microemulsion/Lifshitz regime" with oscillatory correlations, without specifying the
  multicritical topology.

**(b) Symmetric → modulated transition.**
- *Established, at weak coupling (Hartree):* it is **fluctuation-induced first order**
  (Brazovskii1975, Swift1977, Fredrickson1987, Hohenberg1995), and experimentally confirmed in
  diblocks (Bates1988). The lamellar phase is favoured because Z₂ symmetry forbids cubic terms
  (Leibler1980, Kats1993).
- *Strength:* the Brazovskii fluctuation parameter scales like q*/√r (our estimate), i.e.
  ∝ √|Z|. The first-order character therefore **weakens as Z → 0⁻**. Close to the would-be LP the
  shell is unresolved and the Brazovskii analysis does not apply.
- *Caveats:* Barbosa1993 shows that a field (or, by analogy, any parameter that tunes the quartic
  structure) can turn the transition continuous at a tricritical line. Barci2007 shows that an
  intermediate nematic phase is possible in 2D. Neither is expected generically for our 3D
  zero-field model, but a weakly first-order transition at small |Z| may be indistinguishable
  from continuous at accessible L.

**(c) Uniform ↔ modulated transition.**
- *Mean field:* **first order**, with the line tangent to the order–disorder line at the LP
  (Michelson1977).
- *Expectation with fluctuations:* it should stay first order. The two ordered phases break
  different symmetries (translations versus none), so no continuous path exists without an
  intermediate phase. This argument is **[standard]**, not from a specific verified source.

**(d) CEP vs triple point vs tricritical scenarios.**

Two scenarios are possible:
1. **Critical endpoint:** the 3D-Ising uniform line ends on a first-order modulated boundary
   (symmetric/modulated + uniform/modulated). This is the Fisher1990/Fisher1991 structure.
2. **Triple point:** the uniform line becomes first order at a **tricritical point**
   (Riedel1972) before meeting the modulated phase. Three first-order lines (sym–uni, sym–mod,
   uni–mod) then meet at a triple point.

Finite-size signatures **[standard + derived]**:
- *Along the Ising line before the termination:* U4 crossings at 0.4655 (Hasenbusch2010) and
  χ_max ∝ L^{1.964}. Both scenarios share this.
- *Near a tricritical point:* U4 crossing values drift toward the mean-field tricritical value
  1/3 (log-corrected, since d = 3 is the upper tricritical dimension; Deng2004). P(M) develops
  three peaks.
- *Past a tricritical point:* a negative Binder dip ∝ −L^d (Vollmayr1993), latent-heat-like
  double/triple peaks in P(M) and P(Σφ²), ΔF ∝ L^{2} (Lee1990), and χ_max ∝ L³ (Challa1986).
- *At a CEP:* the uniform line stays Ising (crossings at 0.4655 with no drift toward 1/3) right up
  to the endpoint. The coexisting spectator is the *modulated* phase, which shows up as a
  structure-factor peak at q* ≠ 0 in coexistence. Fisher1990/Wilding1997 predict singular
  curvature (diameter) of the first-order boundary near the endpoint.
- *Discriminator:* whether the uniform order parameter's P(M) acquires a central (M = 0,
  symmetric) peak coexisting with ±M peaks before the modulated phase appears. That would mean a
  tricritical point and triple point. If P(M) stays Ising-like until coexistence with a
  q* ≠ 0 state, it is a CEP.

**(e) LRO vs QLRO in the 3D lamellar phase.**
- *Established for smectic-A-type elasticity:* layer fluctuations diverge as ln L in 3D
  (Landau–Peierls). Bragg peaks become power-law (Caillé), with anharmonic log corrections
  (Grinstein1981, Grinstein1982). So there is **no true LRO, only QLRO**, in a rotation-invariant
  continuum.
- *Our model:* the isotropic (∇²φ)² + Z(∇φ)² continuum lamellar phase has exactly smectic-A
  elasticity (no (∇⊥u)² term by rotation invariance) (our derivation). The QCD papers reach the
  same conclusion for chiral density waves (Hidaka2015, Lee2015, Pisarski2019).
- *Lattice caveat:* cubic anisotropy pins layer orientation and should restore true LRO
  asymptotically. Lamellae along lattice axes should be preferred. The crossover length is
  expected to be large when q*a is small (conjectured; no verified source).
- *Practical consequence:* the lamellar order parameter (e.g. |φ_q*|²/L³) should decay only
  weakly (logarithmically or as a small power) with L. This does not invalidate rank-1
  identification.

**(f) Relevance to the QCD moat regime.**
- Our model is the N = 1 (σ-like, Z₂) analogue of the moat/Lifshitz-regime effective theory: a
  negative Z is a "moat."
- The QCD literature claims that the LP is washed out and that inhomogeneous ↔ homogeneous
  transitions are first order with a wide Lifshitz regime (Pisarski2019, Pisarski2019b,
  Pisarski2021b). This claim is supported by FRG (Fu2020). Fu2025 places an actual inhomogeneous
  *instability* at large μ_B, if anywhere.
- Lattice O(N) moat simulations find the condensate disordered into a "quantum pion liquid"
  (Winstel2024). This mechanism relies on N ≥ 2 Goldstone/transverse modes (Pisarski2020).
- Our result that an N = 1 lamellar phase **does** order (rank-1, at least QLRO) is
  complementary. Without Goldstone modes, the Z₂ scalar retains a modulated phase but still loses
  the LP. This is a clean, quotable distinction.

---

## Unverified leads / not in refs.bib

- Caillé, C. R. Acad. Sci. Paris B 274, 891 (1972). The Caillé exponent. There is no DOI, so it is
  excluded under the doi/eprint rule. Its citation appears in Grinstein1981's verified reference
  list. Cite it manually if required.
- Lawrie & Sarbach, "Theory of tricritical points," in Domb–Lebowitz Vol. 9 (1984). No DOI was
  found.
- Peierls (1934) and Landau (1937) on 1D order. Historic, with no DOI. Use Chaikin1995.
- Selke, in Domb–Lebowitz Vol. 15 (1992), the modulated-phases review. A book chapter with no DOI
  located.
- Grest & Sak or Hornreich papers that state *explicitly* that d_L = 4 for the isotropic LP. I did
  not locate a primary paper with this statement in its abstract. Diehl2002 gives the general
  formula 2 + m/2 (for O(n)).
- Vassiliev/Matsen "Monte Carlo phase diagram for diblock copolymer melts," J. Chem. Phys. 124
  (2006), DOI 10.1063/1.2140286. Found via Crossref but not read, so not included.
- Holyst & Schick, J. Chem. Phys. 96, 7728 (1992), DOI 10.1063/1.462372. Lifshitz/disorder lines
  in ternary blends. Metadata found, content unread, so not included.
- Nussinov, Ogilvie, Pannullo, Pisarski, PRL 135, 101904 (2025), "Dilepton production from moaton
  quasiparticles." Possibly useful for QCD framing; not read.
- Pawlowski, Rennecke, Sattler, arXiv:2512.20510, "Inhomogeneous instabilities in high-density
  QCD." Unpublished; not read.
- Rennecke & Yin, arXiv:2609.32563 (part II, correlations). Not read.
- Deng2004's numerical mean-field tricritical Binder ratio: needs a full-text check before
  quoting.
