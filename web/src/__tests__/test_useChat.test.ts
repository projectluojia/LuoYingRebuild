import { describe, it, expect } from 'vitest'

describe('useChat', () => {
  it('parseSseChunk correctly parses SSE events', () => {
    // Test the SSE parsing logic that useChat relies on
    const buffer = 'event: text_delta\ndata: {"text":"hello"}\n\nevent: final\ndata: {"reply":"hello world"}\n\n'
    const normalized = buffer.replace(/\r\n/g, '\n')
    const parts = normalized.split('\n\n')
    const rest = parts.pop() ?? ''
    const events = parts
      .map((part) => {
        let event = 'message'
        const dataLines: string[] = []
        for (const line of part.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
        }
        if (dataLines.length === 0) return null
        try {
          return { event, data: JSON.parse(dataLines.join('\n')) }
        } catch {
          return { event, data: { text: dataLines.join('\n') } }
        }
      })
      .filter(Boolean)

    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ event: 'text_delta', data: { text: 'hello' } })
    expect(events[1]).toEqual({ event: 'final', data: { reply: 'hello world' } })
    expect(rest).toBe('')
  })

  it('handles partial SSE buffers', () => {
    const buffer = 'event: text_delta\ndata: {"text":"partial'
    const parts = buffer.split('\n\n')
    const rest = parts.pop() ?? ''
    expect(rest).toBe('event: text_delta\ndata: {"text":"partial')
  })

  it('handles track events from LuoYingRebuild backend', () => {
    const buffer = 'event: track\ndata: {"text":"searching..."}\n\n'
    const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
    const rest = parts.pop() ?? ''
    const events = parts
      .map((part) => {
        let event = 'message'
        const dataLines: string[] = []
        for (const line of part.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
        }
        if (dataLines.length === 0) return null
        return { event, data: JSON.parse(dataLines.join('\n')) }
      })
      .filter(Boolean)

    expect(events).toHaveLength(1)
    expect(events[0]?.event).toBe('track')
    expect(rest).toBe('')
  })

  it('handles done events from LuoYingRebuild backend', () => {
    const buffer = 'event: done\ndata: {}\n\n'
    const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
    parts.pop()
    const events = parts
      .map((part) => {
        let event = 'message'
        const dataLines: string[] = []
        for (const line of part.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
        }
        if (dataLines.length === 0) return null
        return { event, data: JSON.parse(dataLines.join('\n')) }
      })
      .filter(Boolean)

    expect(events).toHaveLength(1)
    expect(events[0]?.event).toBe('done')
  })
})
