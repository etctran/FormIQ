import '@testing-library/jest-dom/vitest'

if (!URL.createObjectURL) {
  URL.createObjectURL = () => 'blob:mock-url'
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => {}
}
