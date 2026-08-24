// Standard MediaPipe BlazePose 33-landmark topology (indices: 11/12
// shoulders, 13/14 elbows, 15/16 wrists, 23/24 hips, 25/26 knees, 27/28
// ankles), restricted to the core body skeleton -- auxiliary face
// (0-10), hand (17-22), and foot-detail (29-32) landmarks are extracted
// by cv-engine but not connected here, to keep the drawn skeleton clean
// (see spec Key Decision 3 / Non-goals).
export const POSE_CONNECTIONS: readonly [number, number][] = [
  [11, 12], // shoulders
  [11, 13],
  [13, 15], // left arm
  [12, 14],
  [14, 16], // right arm
  [11, 23],
  [12, 24], // torso sides
  [23, 24], // hips
  [23, 25],
  [25, 27], // left leg
  [24, 26],
  [26, 28], // right leg
]
