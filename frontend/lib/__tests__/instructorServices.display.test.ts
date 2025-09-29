import { displayServiceName } from '../instructorServices';

describe('displayServiceName', () => {
  const hydrate = (id: string) => (id === 'ABC123' ? 'Hydrated Name' : undefined);

  it('returns server-provided service_catalog_name when available', () => {
    const result = displayServiceName(
      {
        service_catalog_id: 'ABC123',
        service_catalog_name: 'Server Name',
      },
      hydrate,
    );

    expect(result).toBe('Server Name');
  });

  it('falls back to catalog hydrator when server name missing', () => {
    const result = displayServiceName(
      {
        service_catalog_id: 'ABC123',
        service_catalog_name: null,
      },
      hydrate,
    );

    expect(result).toBe('Hydrated Name');
  });

  it('falls back to ULID string when neither server nor catalog provide a name', () => {
    const result = displayServiceName(
      {
        service_catalog_id: 'XYZ789',
        service_catalog_name: undefined,
      },
      hydrate,
    );

    expect(result).toBe('Service XYZ789');
  });

  it('returns generic label when service_catalog_id is missing', () => {
    const result = displayServiceName(
      {
        service_catalog_id: '',
        service_catalog_name: undefined,
      },
      hydrate,
    );

    expect(result).toBe('Service');
  });
});
