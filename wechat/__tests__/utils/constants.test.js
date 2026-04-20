const { STATUS_GROUPS, filterByGroup } = require('../../utils/constants')

describe('STATUS_GROUPS', () => {
  test('in_progress group includes accepted status', () => {
    expect(STATUS_GROUPS.in_progress).toContain('accepted')
    expect(STATUS_GROUPS.in_progress).toContain('in_progress')
  })

  test('pending group contains created', () => {
    expect(STATUS_GROUPS.pending).toContain('created')
    expect(STATUS_GROUPS.pending).not.toContain('accepted')
  })

  test('completed group contains completed and reviewed', () => {
    expect(STATUS_GROUPS.completed).toContain('completed')
    expect(STATUS_GROUPS.completed).toContain('reviewed')
  })

  test('cancelled group contains all cancellation statuses', () => {
    expect(STATUS_GROUPS.cancelled).toContain('cancelled_by_patient')
    expect(STATUS_GROUPS.cancelled).toContain('cancelled_by_companion')
    expect(STATUS_GROUPS.cancelled).toContain('rejected_by_companion')
    expect(STATUS_GROUPS.cancelled).toContain('expired')
  })

  test('every status belongs to exactly one group', () => {
    const allStatuses = Object.values(STATUS_GROUPS).flat()
    const unique = [...new Set(allStatuses)]
    expect(allStatuses.length).toBe(unique.length)
  })
})

describe('filterByGroup', () => {
  const orders = [
    { id: 1, status: 'created' },
    { id: 2, status: 'accepted' },
    { id: 3, status: 'in_progress' },
    { id: 4, status: 'completed' },
    { id: 5, status: 'reviewed' },
    { id: 6, status: 'cancelled_by_patient' },
  ]

  test('in_progress group returns accepted and in_progress orders', () => {
    const result = filterByGroup('in_progress', orders)
    expect(result.map(o => o.id)).toEqual([2, 3])
  })

  test('pending group returns only created orders', () => {
    const result = filterByGroup('pending', orders)
    expect(result.map(o => o.id)).toEqual([1])
  })

  test('completed group returns completed and reviewed orders', () => {
    const result = filterByGroup('completed', orders)
    expect(result.map(o => o.id)).toEqual([4, 5])
  })

  test('cancelled group returns cancelled orders', () => {
    const result = filterByGroup('cancelled', orders)
    expect(result.map(o => o.id)).toEqual([6])
  })
})
