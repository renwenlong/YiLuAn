const haptic = require('../../utils/haptic');

describe('haptic (P-03)', () => {
  beforeEach(() => {
    // Reset wx mocks
    global.wx.vibrateShort = jest.fn((opts) => {
      if (opts && opts.success) opts.success();
    });
    global.wx.removeStorageSync('user_settings');
  });

  test('returns true when haptic fires successfully', async () => {
    const ok = await haptic('light');
    expect(ok).toBe(true);
    expect(global.wx.vibrateShort).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'light' })
    );
  });

  test('defaults to light when given invalid type', async () => {
    await haptic('unknown');
    expect(global.wx.vibrateShort).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'light' })
    );
  });

  test('returns false when user disabled haptic in settings', async () => {
    global.wx.setStorageSync('user_settings', { hapticDisabled: true });
    const ok = await haptic();
    expect(ok).toBe(false);
    expect(global.wx.vibrateShort).not.toHaveBeenCalled();
  });

  test('returns false silently when wx.vibrateShort is missing', async () => {
    delete global.wx.vibrateShort;
    const ok = await haptic();
    expect(ok).toBe(false);
  });

  test('returns false when vibrateShort fails', async () => {
    global.wx.vibrateShort = jest.fn((opts) => {
      if (opts && opts.fail) opts.fail({ errMsg: 'vibrate fail' });
    });
    const ok = await haptic();
    expect(ok).toBe(false);
  });

  test('convenience helpers work', async () => {
    await haptic.light();
    await haptic.medium();
    await haptic.heavy();
    const calls = global.wx.vibrateShort.mock.calls.map((c) => c[0].type);
    expect(calls).toEqual(['light', 'medium', 'heavy']);
  });
});
