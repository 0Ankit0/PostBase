import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/models/platform_surface_state.dart';

void main() {
  test('returns success when data is healthy', () {
    final state = deriveMobilePlatformSurfaceState(
      hasError: false,
      isPermissionDenied: false,
      isFromCache: false,
      isStale: false,
      hasDegradedBackend: false,
    );

    expect(state, MobilePlatformSurfaceState.success);
  });

  test('returns failure when backend errors without permission issue', () {
    final state = deriveMobilePlatformSurfaceState(
      hasError: true,
      isPermissionDenied: false,
      isFromCache: false,
      isStale: false,
      hasDegradedBackend: false,
    );

    expect(state, MobilePlatformSurfaceState.failure);
  });

  test('returns permissionDenied when API blocks platform read access', () {
    final state = deriveMobilePlatformSurfaceState(
      hasError: true,
      isPermissionDenied: true,
      isFromCache: false,
      isStale: false,
      hasDegradedBackend: false,
    );

    expect(state, MobilePlatformSurfaceState.permissionDenied);
  });

  test('returns staleOfflineCache when rendering cached stale status', () {
    final state = deriveMobilePlatformSurfaceState(
      hasError: false,
      isPermissionDenied: false,
      isFromCache: true,
      isStale: true,
      hasDegradedBackend: false,
    );

    expect(state, MobilePlatformSurfaceState.staleOfflineCache);
  });

  test('returns degradedBackend when partial backend data is degraded', () {
    final state = deriveMobilePlatformSurfaceState(
      hasError: false,
      isPermissionDenied: false,
      isFromCache: false,
      isStale: false,
      hasDegradedBackend: true,
    );

    expect(state, MobilePlatformSurfaceState.degradedBackend);
  });
}
