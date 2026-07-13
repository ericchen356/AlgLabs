/** T18 — trainer phase machines as pure reducers (§12.3 random / §12.4 grind).
 * Hold-based model: press = 'down', release = 'up'. */
import { describe, expect, it } from 'vitest'
import {
  fmtMs,
  initialMachine,
  isRunning,
  liveSplits,
  pushSession,
  stepMachine,
  type SessionEntry,
  type TrainerInput,
} from './machine'

describe('random mode: hold to recognize, release to solve, press to stop', () => {
  it('walks idle -down-> recognition -up-> execution -down-> done -down-> idle', () => {
    const idle = initialMachine('random')
    expect(idle).toEqual({
      mode: 'random',
      phase: 'idle',
      phaseStart: null,
      recogMs: 0,
      execMs: 0,
    })
    expect(isRunning(idle)).toBe(false)

    // press: idle → recognition (recognition runs WHILE held)
    const a = stepMachine(idle, 'down', 1000)
    expect(a.event).toBe('startRecognition')
    expect(a.state.phase).toBe('recognition')
    expect(a.state.phaseStart).toBe(1000)
    expect(isRunning(a.state)).toBe(true)
    // live readout ticks while the frozen splits stay 0
    expect(liveSplits(a.state, 1400)).toEqual({ recog: 400, exec: 0, total: 400 })

    // release: recognition → execution, recognition split frozen
    const b = stepMachine(a.state, 'up', 1500)
    expect(b.event).toBe('startExecution')
    expect(b.state.phase).toBe('execution')
    expect(b.state.recogMs).toBe(500)
    expect(b.state.phaseStart).toBe(1500)
    expect(liveSplits(b.state, 2100)).toEqual({ recog: 500, exec: 600, total: 1100 })

    // press: execution → done, execution split frozen, total = recog + exec
    const c = stepMachine(b.state, 'down', 2400)
    expect(c.event).toBe('finish')
    expect(c.state.phase).toBe('done')
    expect(c.state.execMs).toBe(900)
    expect(c.state.phaseStart).toBeNull()
    expect(isRunning(c.state)).toBe(false)
    expect(liveSplits(c.state, 99999)).toEqual({ recog: 500, exec: 900, total: 1400 })

    // press: done → idle (component fetches the next scramble on this event)
    const d = stepMachine(c.state, 'down', 3000)
    expect(d.event).toBe('next')
    expect(d.state).toEqual(initialMachine('random'))
  })

  it('ignores the release that follows a stop/next press (no double-advance)', () => {
    let m = initialMachine('random')
    m = stepMachine(m, 'down', 0).state // recognition
    m = stepMachine(m, 'up', 100).state // execution
    const stopped = stepMachine(m, 'down', 300) // done
    expect(stopped.event).toBe('finish')
    // the physical release of that stop press lands in `done` and does nothing
    const strayUp = stepMachine(stopped.state, 'up', 320)
    expect(strayUp.event).toBe('none')
    expect(strayUp.state).toBe(stopped.state)
    // press → next (idle); its release lands in idle and does nothing
    const next = stepMachine(stopped.state, 'down', 500)
    expect(next.event).toBe('next')
    const strayUp2 = stepMachine(next.state, 'up', 520)
    expect(strayUp2.event).toBe('none')
    expect(strayUp2.state.phase).toBe('idle')
  })

  it('idle ignores a release (stray keyup with no keydown)', () => {
    const idle = initialMachine('random')
    const r = stepMachine(idle, 'up', 100)
    expect(r.event).toBe('none')
    expect(r.state).toBe(idle)
  })

  it('resets stale splits when a new solve starts', () => {
    let m = initialMachine('random')
    for (const [inp, t] of [
      ['down', 0],
      ['up', 100],
      ['down', 250],
      ['down', 300],
    ] as [TrainerInput, number][]) {
      m = stepMachine(m, inp, t).state // full solve + next
    }
    const restarted = stepMachine(m, 'down', 400).state // idle → recognition again
    expect(restarted.recogMs).toBe(0)
    expect(restarted.execMs).toBe(0)
    expect(restarted.phaseStart).toBe(400)
  })
})

describe('grind mode: hold to arm, release to start, press to stop (§12.4)', () => {
  it('walks idle -down-> armed -up-> execution -down-> done -down-> idle', () => {
    const idle = initialMachine('grind')

    // press: idle → armed, NO timer running yet
    const a = stepMachine(idle, 'down', 500)
    expect(a.event).toBe('arm')
    expect(a.state.phase).toBe('armed')
    expect(a.state.phaseStart).toBeNull()
    expect(isRunning(a.state)).toBe(false)
    // armed does not tick
    expect(liveSplits(a.state, 900)).toEqual({ recog: 0, exec: 0, total: 0 })

    // release: armed → execution (timer starts on release)
    const b = stepMachine(a.state, 'up', 800)
    expect(b.event).toBe('startExecution')
    expect(b.state.phase).toBe('execution')
    expect(b.state.phaseStart).toBe(800)
    expect(liveSplits(b.state, 1100)).toEqual({ recog: 0, exec: 300, total: 300 })

    // press: execution → done, recognition never times
    const c = stepMachine(b.state, 'down', 2300)
    expect(c.event).toBe('finish')
    expect(c.state.phase).toBe('done')
    expect(c.state.recogMs).toBe(0)
    expect(c.state.execMs).toBe(1500)
    expect(liveSplits(c.state, 9999)).toEqual({ recog: 0, exec: 1500, total: 1500 })

    const d = stepMachine(c.state, 'down', 2500)
    expect(d.event).toBe('next')
    expect(d.state).toEqual(initialMachine('grind'))
  })

  it('armed ignores an extra press; only release starts the timer', () => {
    let m = initialMachine('grind')
    m = stepMachine(m, 'down', 0).state // armed
    const extra = stepMachine(m, 'down', 50)
    expect(extra.event).toBe('none')
    expect(extra.state.phase).toBe('armed')
  })
})

describe('session strip (§12.3: last 6, newest first)', () => {
  it('pushes newest first and keeps at most 6 entries', () => {
    let s: SessionEntry[] = []
    for (let i = 1; i <= 8; i++) s = pushSession(s, { ms: i * 1000, isPB: i === 3 })
    expect(s).toHaveLength(6)
    expect(s.map((e) => e.ms)).toEqual([8000, 7000, 6000, 5000, 4000, 3000])
    expect(s[5].isPB).toBe(true)
  })
})

describe('timer format (§12.3: (ms/1000).toFixed(2))', () => {
  it('formats milliseconds as seconds with two decimals', () => {
    expect(fmtMs(0)).toBe('0.00')
    expect(fmtMs(1234)).toBe('1.23')
    expect(fmtMs(1235.5)).toBe('1.24')
    expect(fmtMs(60000)).toBe('60.00')
  })
})
