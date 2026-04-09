enum MobilePlatformSurfaceState {
  success,
  failure,
  permissionDenied,
  degradedBackend,
  staleOfflineCache,
}

MobilePlatformSurfaceState deriveMobilePlatformSurfaceState({
  required bool hasError,
  required bool isPermissionDenied,
  required bool isFromCache,
  required bool isStale,
  required bool hasDegradedBackend,
}) {
  if (hasError && isPermissionDenied) {
    return MobilePlatformSurfaceState.permissionDenied;
  }
  if (hasError) {
    return MobilePlatformSurfaceState.failure;
  }
  if (isFromCache || isStale) {
    return MobilePlatformSurfaceState.staleOfflineCache;
  }
  if (hasDegradedBackend) {
    return MobilePlatformSurfaceState.degradedBackend;
  }
  return MobilePlatformSurfaceState.success;
}
