import { describe, expect, it } from 'vitest'
import { duration, eventLabel, number, shortModel } from './utils'
describe('research values stay distinct from missing data', () => {
  it('preserves real zeros and marks missing values', () => {
    expect(number(0)).toBe('0')
    expect(number(undefined)).toBe('—')
    expect(duration(0)).toBe('0.0s')
    expect(duration(undefined)).toBe('—')
  })
  it('formats long durations and normalized event types', () => {
    expect(duration(187000)).toBe('3m 7s')
    expect(eventLabel('tool_result')).toBe('Tool result')
    expect(shortModel('openrouter/provider/model')).toBe('model')
  })
})
