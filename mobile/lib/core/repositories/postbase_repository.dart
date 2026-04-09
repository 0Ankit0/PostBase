import '../error/error_handler.dart';
import '../models/paginated_response.dart';
import '../models/postbase_status.dart';
import '../network/api_endpoints.dart';
import '../network/dio_client.dart';

class PostBaseRepository {
  PostBaseRepository(this._dioClient);

  final DioClient _dioClient;

  Future<List<PostBaseProjectRead>> listProjects() async {
    try {
      final response = await _dioClient.dio.get(ApiEndpoints.postBaseProjects);
      final paginated = PaginatedResponse<Map<String, dynamic>>.fromJson(
        response.data as Map<String, dynamic>,
        (json) => json,
      );
      return paginated.items
          .map((item) => PostBaseProjectRead.fromJson(item))
          .toList();
    } catch (e) {
      throw ErrorHandler.handle(e);
    }
  }

  Future<PostBaseProjectOverview> getProjectOverview(String projectId) async {
    try {
      final response = await _dioClient.dio
          .get(ApiEndpoints.postBaseProjectOverview(projectId));
      return PostBaseProjectOverview.fromJson(
        response.data as Map<String, dynamic>,
      );
    } catch (e) {
      throw ErrorHandler.handle(e);
    }
  }

  Future<PostBaseCapabilityHealthReport> getCapabilityHealth(
    String environmentId,
  ) async {
    try {
      final response = await _dioClient.dio
          .get(ApiEndpoints.postBaseCapabilityHealth(environmentId));
      return PostBaseCapabilityHealthReport.fromJson(
        response.data as Map<String, dynamic>,
      );
    } catch (e) {
      throw ErrorHandler.handle(e);
    }
  }

  Future<PostBasePlatformSnapshot> getPlatformStatusSnapshot({
    List<PostBaseProjectStatus>? previousStatuses,
  }) async {
    final now = DateTime.now().toUtc();
    try {
      final projects = await listProjects();
      final statuses = <PostBaseProjectStatus>[];
      var degradedCount = 0;

      for (final project in projects) {
        try {
          final overview = await getProjectOverview(project.id);
          PostBaseCapabilityHealthReport? health;
          String? degradedReason;
          final primaryEnvironment = overview.environments.isNotEmpty
              ? overview.environments.first.environmentId
              : null;
          if (primaryEnvironment != null && primaryEnvironment.isNotEmpty) {
            try {
              health = await getCapabilityHealth(primaryEnvironment);
            } catch (e) {
              degradedCount += 1;
              degradedReason = 'Capability health unavailable: ${ErrorHandler.handle(e).message}';
            }
          }
          statuses.add(
            PostBaseProjectStatus(
              project: project,
              overview: overview,
              primaryEnvironmentHealth: health,
              hasDegradedBackendState: degradedReason != null,
              degradedReason: degradedReason,
            ),
          );
        } catch (e) {
          degradedCount += 1;
        }
      }

      return PostBasePlatformSnapshot(
        statuses: statuses,
        isFromCache: false,
        isStale: false,
        fetchedAt: now,
        warning: degradedCount > 0
            ? '$degradedCount project(s) returned degraded backend data.'
            : null,
      );
    } catch (e) {
      if (previousStatuses != null && previousStatuses.isNotEmpty) {
        return PostBasePlatformSnapshot(
          statuses: previousStatuses,
          isFromCache: true,
          isStale: true,
          fetchedAt: now,
          warning:
              'Offline or backend failure. Showing cached read-only platform status.',
        );
      }
      throw ErrorHandler.handle(e);
    }
  }
}
