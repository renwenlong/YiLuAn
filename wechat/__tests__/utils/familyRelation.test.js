const {
  relationLabel,
  RELATION_LABELS,
  RELATION_OPTIONS,
} = require('../../utils/familyRelation')

describe('utils/familyRelation', () => {
  test('relationLabel maps all known enum values to Chinese labels', () => {
    expect(relationLabel('self')).toBe('本人')
    expect(relationLabel('parent')).toBe('父母')
    expect(relationLabel('spouse')).toBe('配偶')
    expect(relationLabel('child')).toBe('子女')
    expect(relationLabel('sibling')).toBe('兄弟姐妹')
    expect(relationLabel('grandparent')).toBe('祖父母')
    expect(relationLabel('relative')).toBe('亲戚')
    expect(relationLabel('friend')).toBe('朋友')
    expect(relationLabel('other')).toBe('其他')
  })

  test('relationLabel falls back to "其他" for unknown / empty', () => {
    expect(relationLabel('')).toBe('其他')
    expect(relationLabel(null)).toBe('其他')
    expect(relationLabel(undefined)).toBe('其他')
    expect(relationLabel('unknown_value')).toBe('其他')
  })

  test('RELATION_LABELS contains all 9 backend enum keys', () => {
    const keys = Object.keys(RELATION_LABELS)
    expect(keys).toEqual(
      expect.arrayContaining([
        'self', 'parent', 'spouse', 'child', 'sibling',
        'grandparent', 'relative', 'friend', 'other',
      ])
    )
  })

  test('RELATION_OPTIONS excludes "self" (picker is for non-self family)', () => {
    const values = RELATION_OPTIONS.map(o => o.value)
    expect(values).not.toContain('self')
    expect(values.length).toBeGreaterThanOrEqual(8)
  })
})
