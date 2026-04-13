/* Auto-generated from backend/openapi/openapi.json. */
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RequestOptions {
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  headers?: Record<string, string>;
}

export interface Transport {
  request<T = unknown>(method: HttpMethod, path: string, options?: RequestOptions): Promise<T>;
}

export class PostBaseSdkClient {
  constructor(private readonly transport: Transport) {}

  list_projects_api_v1_projects_get(options: RequestOptions = {}): Promise<unknown> {
    return this.transport.request('GET', '/api/v1/projects', options);
  }

  list_provider_catalog_api_v1_provider_catalog_get(options: RequestOptions = {}): Promise<unknown> {
    return this.transport.request('GET', '/api/v1/provider-catalog', options);
  }
}
