// Jest's test environment has no real frame timing, so an Animated.loop can spin synchronously
// inside react-test-renderer's act() instead of ticking on wall-clock time — hanging the test
// process rather than animating. Nothing in this repo's tests asserts on animation behavior, so
// looping animations skip starting entirely under test.
export const isTestEnv = process.env.JEST_WORKER_ID !== undefined;
