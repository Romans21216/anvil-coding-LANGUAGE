# Master backlog mirror — GitHub issue #23

Synced from [issue #23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) on 2026-10-27. Issue #23 is the source of truth for the 450 backlog entries.

# ANVIL LANGUAGE AND GAME ENGINE — 450-ITEM FIX AND IMPROVEMENT BACKLOG

Based on the updated October 27, 2026 evaluation. Items include missing features, existing systems that need improvement, reliability fixes, and proposed future capabilities. Features already verified in the report are marked as enhancements rather than missing implementations.

## 1. CORE LANGUAGE AND SYNTAX

1. Expand the current numeric type system to support additional data types.
2. Add a proper Boolean data type.
3. Add a complete string data type.
4. Add string concatenation.
5. Add string comparison.
6. Add string interpolation.
7. Add string formatting.
8. Add immutable variables.
9. Add constant declarations.
10. Add explicit numeric type declarations.
11. Add integer types.
12. Add floating-point types with documented precision.
13. Add safe numeric conversion functions.
14. Add explicit type casting.
15. Add type inference where appropriate.
16. Add user-defined structures.
17. Add enumerations.
18. Add optional values.
19. Add structured error-result values.
20. Add named function arguments.
21. Add default function arguments.
22. Add function overloading or an equivalent reusable-function mechanism.
23. Add anonymous functions if compatible with Anvil's language design.
24. Add function references or callbacks.
25. Add methods associated with structured values.
26. Add namespaces.
27. Add modules.
28. Add import statements.
29. Add multi-file compilation.
30. Add module visibility rules.
31. Add public and private declarations.
32. Add explicit variable lifetime rules.
33. Improve nested scope handling.
34. Add shadowing rules and diagnostics.
35. Add compound assignment operators.
36. Add increment and decrement operations where appropriate.
37. Add conditional expressions.
38. Add switch or match expressions.
39. Add break statements for loops.
40. Add continue statements for loops.
41. Improve the existing numeric for-loop syntax and diagnostics.
42. Improve the existing while-loop validation.
43. Add iterator-based loops for collections.
44. Add collection traversal utilities.
45. Formalize operator precedence and associativity.
46. Add short-circuit Boolean evaluation.
47. Add explicit overflow behavior.
48. Add division-by-zero diagnostics.
49. Add language feature versioning.
50. Publish a complete formal language specification.

## 2. ARRAYS, COLLECTIONS, AND MEMORY

51. Extend the implemented fixed-size arrays with dynamic arrays.
52. Add array resizing.
53. Add array append operations.
54. Add array removal operations.
55. Add array insertion operations.
56. Add array slicing.
57. Add array copying.
58. Add array sorting.
59. Add array searching.
60. Add array filtering.
61. Add array mapping utilities.
62. Add multidimensional arrays.
63. Add nested collections.
64. Add dictionaries or maps.
65. Add sets.
66. Add queues.
67. Add stacks.
68. Add reusable collection iterators.
69. Add collection capacity management.
70. Add collection length and capacity queries.
71. Extend checked indexing to all new collection types.
72. Add safe access functions for collections.
73. Add collection serialization.
74. Add structured-value arrays.
75. Add configurable collection memory limits.
76. Improve diagnostics for array allocation failures.
77. Benchmark the existing heap-backed local arrays.
78. Optimize repeated local-array allocations.
79. Investigate reusable allocation pools.
80. Add configurable per-function allocation limits.
81. Add configurable active-call memory limits.
82. Add memory allocation profiling.
83. Add memory leak detection.
84. Add use-after-free prevention for future reference types.
85. Add ownership and lifetime rules.
86. Add resource cleanup guarantees.
87. Add automatic cleanup for error paths.
88. Add memory fragmentation testing.
89. Add large-array stress tests.
90. Add recursive allocation stress tests.
91. Add collection memory usage reporting.
92. Add stack usage monitoring.
93. Add heap usage monitoring.
94. Add configurable memory budgets.
95. Add out-of-memory recovery policies.
96. Add resource handles with validity checks.
97. Add resource reference counting where appropriate.
98. Add explicit resource release operations.
99. Add memory diagnostics in debug builds.
100. Document memory and collection behavior.

## 3. COMPILER AND CODE GENERATION

101. Separate lexical analysis from parsing.
102. Separate parsing from semantic validation.
103. Separate semantic validation from C generation.
104. Separate C generation from build orchestration.
105. Add an intermediate representation for Anvil programs.
106. Add a formal symbol table.
107. Add source-location tracking throughout compilation.
108. Improve syntax error recovery.
109. Report multiple independent errors in one compilation.
110. Add precise diagnostics for type mismatches.
111. Add precise diagnostics for undefined variables.
112. Add precise diagnostics for undefined functions.
113. Add precise diagnostics for incorrect argument counts.
114. Add precise diagnostics for invalid return values.
115. Add precise diagnostics for invalid array declarations.
116. Add precise diagnostics for invalid array indexing.
117. Add unreachable-code warnings.
118. Add unused-variable warnings.
119. Add unused-function warnings.
120. Add uninitialized-variable analysis.
121. Add constant folding.
122. Add constant propagation.
123. Add dead-code elimination.
124. Add redundant expression elimination.
125. Add basic control-flow analysis.
126. Add call-graph generation.
127. Add recursion-depth diagnostics or configurable guards.
128. Add compiler optimization levels.
129. Add debug-symbol generation.
130. Add source mapping between Anvil and generated C.
131. Add deterministic generated-code formatting.
132. Add generated-code inspection commands.
133. Add compiler output validation.
134. Add incremental compilation.
135. Add compilation caching.
136. Add dependency tracking between source files.
137. Add parallel compilation where beneficial.
138. Add compiler performance profiling.
139. Add compiler fuzz testing.
140. Add parser fuzz testing.
141. Add semantic analyzer regression tests.
142. Add generated C regression tests.
143. Add compiler compatibility tests.
144. Add compiler version reporting.
145. Add clear compiler exit codes.
146. Add machine-readable compiler diagnostics.
147. Add compiler warning levels.
148. Add warnings-as-errors support.
149. Add reproducible build output.
150. Add compiler architecture documentation.

## 4. CPU AND GPU RENDERING

151. Implement a dual-backend rendering architecture.
152. Preserve the existing CPU software renderer.
153. Add a GPU-accelerated rendering backend.
154. Add explicit CPU rendering selection.
155. Add explicit GPU rendering selection.
156. Add automatic rendering backend selection.
157. Add rendering backend configuration in project manifests.
158. Add rendering backend configuration through Anvil code.
159. Define whether backend switching is supported during runtime.
160. Add graphics hardware capability detection.
161. Add GPU driver compatibility checks.
162. Add configurable GPU-to-CPU fallback behavior.
163. Add clear errors when a requested backend is unavailable.
164. Add backend initialization diagnostics.
165. Add backend shutdown and cleanup handling.
166. Add backend resource ownership rules.
167. Standardize core drawing commands across backends.
168. Add cross-backend visual consistency tests.
169. Add backend-specific feature detection.
170. Add backend-specific performance reporting.
171. Add configurable rendering resolution.
172. Add dynamic window resizing.
173. Remove the fixed-size rendering restriction.
174. Add fullscreen mode.
175. Add borderless fullscreen mode.
176. Add display resolution selection.
177. Add monitor selection.
178. Add high-DPI display support.
179. Add configurable vertical synchronization.
180. Add frame-rate limiting.
181. Add adaptive frame pacing.
182. Add resolution scaling.
183. Add dynamic resolution scaling.
184. Add configurable anti-aliasing.
185. Add robust near-plane clipping.
186. Add far-plane clipping.
187. Improve depth buffering.
188. Add stencil buffering where supported.
189. Add viewport management.
190. Add render targets.
191. Add offscreen rendering.
192. Add framebuffer capture.
193. Add screenshot export.
194. Add GPU resource profiling.
195. Add CPU rendering profiling.
196. Add rendering performance overlays.
197. Add graphics API abstraction.
198. Add Direct3D support through the GPU backend.
199. Add optional Vulkan support.
200. Add optional OpenGL support.

## 5. GRAPHICS, TEXTURES, AND MATERIALS

201. Add texture file loading.
202. Add texture unloading.
203. Add texture caching.
204. Add texture compression support.
205. Add texture filtering.
206. Add mipmapping.
207. Add texture wrapping modes.
208. Add texture atlases.
209. Add sprite rendering.
210. Add sprite sheets.
211. Add sprite animation.
212. Add sprite rotation and scaling.
213. Add nine-slice sprite rendering.
214. Add 2D tilemap rendering.
215. Add tilemap collision integration.
216. Add 3D mesh importing.
217. Add support for a common mesh interchange format.
218. Add mesh validation.
219. Add mesh optimization.
220. Add mesh instancing.
221. Add mesh level-of-detail support.
222. Add material definitions.
223. Add material property editing.
224. Add diffuse texture mapping.
225. Add normal mapping.
226. Add roughness mapping.
227. Add metallic material properties.
228. Add transparency and alpha blending.
229. Add configurable blend modes.
230. Add directional lights.
231. Add point lights.
232. Add spotlights.
233. Add configurable ambient lighting.
234. Add shadow mapping for supported GPU backends.
235. Add shadow quality settings.
236. Add gamma correction.
237. Add color space management.
238. Add HDR rendering where supported.
239. Add tone mapping.
240. Add bloom as an optional effect.
241. Add post-processing effects.
242. Add configurable shader programs.
243. Add shader compilation diagnostics.
244. Add shader hot reloading.
245. Add particle rendering.
246. Add particle emitters.
247. Add configurable particle lifetimes.
248. Add particle collision options.
249. Add graphics resource budgeting.
250. Add visual rendering regression tests.

## 6. 3D ENGINE AND CAMERA SYSTEMS

251. Add full 3D transformation support.
252. Add translation, rotation, and scaling utilities.
253. Add transformation hierarchies.
254. Add parent-child object relationships.
255. Add world-space and local-space transforms.
256. Add quaternion rotations.
257. Add matrix transformation utilities.
258. Add multiple active camera configurations.
259. Add orthographic camera support.
260. Improve perspective camera configuration.
261. Add camera movement smoothing.
262. Add camera rotation constraints.
263. Add first-person camera utilities.
264. Add third-person camera utilities.
265. Add orbit camera controls.
266. Add camera follow behavior.
267. Add camera shake.
268. Add camera transitions.
269. Add configurable camera clipping planes.
270. Add camera projection tests.
271. Add frustum culling.
272. Add object visibility testing.
273. Add spatial partitioning.
274. Add bounding volume utilities.
275. Add object picking with rays.
276. Add 3D collision queries.
277. Add terrain rendering.
278. Add heightmap terrain support.
279. Add terrain collision integration.
280. Add skybox rendering.
281. Add environment mapping.
282. Add 3D animation playback.
283. Add skeletal animation.
284. Add animation blending.
285. Add animation state machines.
286. Add model attachment points.
287. Add 3D debug drawing.
288. Add scene hierarchy inspection.
289. Add 3D object serialization.
290. Add 3D scene loading.
291. Add 3D scene unloading.
292. Add scene streaming.
293. Add level-of-detail management.
294. Add instanced object rendering.
295. Add object occlusion handling.
296. Add 3D spatial audio integration.
297. Add configurable world units.
298. Add large-world coordinate handling.
299. Add 3D performance benchmarks.
300. Add 3D engine integration tests.

## 7. PHYSICS AND COLLISION SYSTEM

301. Improve the existing bounded 2D circle physics prototype.
302. Make the current 128-body limit configurable where feasible.
303. Add rectangle collision bodies.
304. Add polygon collision bodies.
305. Add capsule collision bodies.
306. Add 3D sphere collision bodies.
307. Add 3D box collision bodies.
308. Add convex 3D collision shapes.
309. Add collision meshes.
310. Add continuous collision detection.
311. Add friction.
312. Add restitution configuration.
313. Add physics joints.
314. Add distance constraints.
315. Add hinge constraints.
316. Add spring constraints.
317. Add trigger volumes.
318. Add collision layers.
319. Add collision masks.
320. Add collision callbacks.
321. Add collision enter events.
322. Add collision exit events.
323. Add collision stay events.
324. Add physics raycasting.
325. Add shape casting.
326. Add overlap queries.
327. Add broad-phase collision acceleration.
328. Improve narrow-phase collision resolution.
329. Add configurable solver iterations.
330. Add physics sleeping.
331. Add rigid-body mass properties.
332. Add angular velocity.
333. Add torque.
334. Add rotational inertia.
335. Add configurable gravity fields.
336. Add kinematic bodies.
337. Add static bodies.
338. Add dynamic bodies.
339. Add physics materials.
340. Add character controller utilities.
341. Add collision debug visualization.
342. Add physics performance profiling.
343. Add deterministic simulation tests.
344. Add high-speed collision tests.
345. Add physics stress tests.
346. Add collision stability tests.
347. Add physics save-state support.
348. Add physics rollback support if required by networking.
349. Add configurable physics world limits.
350. Document the physics solver and its limitations.

## 8. RAY TRACING

351. Benchmark the existing CPU BVH ray tracer.
352. Improve BVH construction efficiency.
353. Improve BVH traversal efficiency.
354. Increase the 32-sphere batch limit after performance testing.
355. Add configurable ray-tracing resolution.
356. Add configurable ray-tracing sample counts.
357. Add ray-traced triangles.
358. Add ray-traced meshes.
359. Add ray-traced material properties.
360. Add reflections.
361. Add refractions.
362. Add transparent materials.
363. Add rough reflective surfaces.
364. Add configurable ray-traced lights.
365. Add soft shadows.
366. Add ambient occlusion.
367. Add progressive rendering.
368. Add denoising.
369. Add ray-tracing quality presets.
370. Add ray-tracing memory budgets.
371. Add ray-tracing backend abstraction.
372. Preserve CPU BVH as a supported backend.
373. Add optional GPU ray tracing.
374. Add optional DXR support.
375. Add optional Embree acceleration.
376. Add backend capability detection.
377. Add backend fallback policies.
378. Add ray-tracing backend configuration.
379. Add CPU-versus-GPU ray-tracing benchmarks.
380. Add ray-tracing correctness tests.

## 9. AUDIO, INPUT, AND USER INTERFACE

381. Add audio file loading.
382. Add sound effect playback.
383. Add music playback.
384. Add audio mixing.
385. Add master volume controls.
386. Add per-channel volume controls.
387. Add audio looping.
388. Add audio fading.
389. Add positional audio.
390. Add audio resource cleanup.
391. Add mouse input support.
392. Add mouse position tracking.
393. Add mouse button events.
394. Add mouse wheel input.
395. Add gamepad support.
396. Add controller mapping.
397. Add configurable key bindings.
398. Add input action mapping.
399. Add input focus handling.
400. Add text input handling.
401. Add UI buttons.
402. Add UI labels.
403. Add UI panels.
404. Add UI sliders.
405. Add UI checkboxes.
406. Add UI text fields.
407. Add UI layout containers.
408. Add UI scaling.
409. Add keyboard navigation for UI.
410. Add accessible focus indicators.

## 10. MULTIPLAYER AND NETWORKING

411. Replace numeric-only UDP messages with structured packets.
412. Add packet serialization.
413. Add packet deserialization.
414. Add packet validation.
415. Add packet size limits.
416. Add network protocol versioning.
417. Add multiple-peer support.
418. Add peer connection management.
419. Add peer disconnection management.
420. Add connection timeouts.
421. Add reconnection handling.
422. Add reliable message delivery where needed.
423. Add ordered message delivery where needed.
424. Add packet sequence numbers.
425. Add latency measurement.
426. Add packet loss measurement.
427. Add entity state replication.
428. Add player state synchronization.
429. Add interpolation.
430. Add optional client prediction.
431. Add server reconciliation.
432. Add server-authoritative simulation support.
433. Add network authentication.
434. Add encryption for Internet communication.
435. Add network rate limiting.
436. Add malformed-packet fuzz testing.
437. Add network debugging tools.
438. Add simulated packet loss testing.
439. Add simulated latency testing.
440. Add multiplayer stress testing.

## 11. DEVELOPER TOOLS, TESTING, AND RELEASES

441. Expand the existing VS Code extension with autocomplete.
442. Add live compiler diagnostics to the editor.
443. Add go-to-definition and find-references support.
444. Add a debugger with breakpoints.
445. Add variable and call-stack inspection.
446. Add a one-command build-and-run workflow.
447. Add automated CPU and GPU performance benchmarks.
448. Expand cross-platform build and runtime support beyond Windows/MSVC.
449. Keep the existing automated tests, extension validation, and QA reports synchronized with every release.
450. Establish stable release, compatibility, regression-testing, and production-readiness criteria.