import { getInstantFallback, triggerGeneration } from '../backendClient';

jest.mock('expo-constants', () => ({
  __esModule: true,
  default: {
    expoConfig: {
      extra: {
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
        backendUrl: 'https://test-backend.example.com',
      },
    },
  },
}));

const mockGetSession = jest.fn();
jest.mock('../supabase', () => ({
  supabase: { auth: { getSession: (...args: unknown[]) => mockGetSession(...args) } },
}));

const originalFetch = global.fetch;

beforeEach(() => {
  jest.clearAllMocks();
  mockGetSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  global.fetch = jest.fn();
});

afterAll(() => {
  global.fetch = originalFetch;
});

describe('triggerGeneration', () => {
  it('POSTs with the session access token and returns the parsed body', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ week_start: '2026-09-07' }),
    });

    const result = await triggerGeneration();

    expect(result).toEqual({ week_start: '2026-09-07' });
    expect(global.fetch).toHaveBeenCalledWith(
      'https://test-backend.example.com/generation/trigger',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    );
  });

  it('throws when there is no active session, rather than calling the backend unauthenticated', async () => {
    mockGetSession.mockResolvedValue({ data: { session: null } });

    await expect(triggerGeneration()).rejects.toThrow('No active session');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('throws when the backend responds with a non-2xx status', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false, status: 500 });

    await expect(triggerGeneration()).rejects.toThrow('500');
  });
});

describe('getInstantFallback', () => {
  it('GETs with the session access token and returns the parsed items', async () => {
    const items = [
      {
        day: '2026-09-10',
        slot: 'morning',
        item_type: 'breakfast',
        dish_id: 'd1',
        dish_name: 'Idli',
      },
    ];
    (global.fetch as jest.Mock).mockResolvedValue({ ok: true, json: () => Promise.resolve(items) });

    const result = await getInstantFallback();

    expect(result).toEqual(items);
    expect(global.fetch).toHaveBeenCalledWith(
      'https://test-backend.example.com/plan/instant-fallback',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    );
  });
});
