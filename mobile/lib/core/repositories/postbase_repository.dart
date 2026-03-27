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

  Future<List<PostBaseProjectStatus>> getPlatformStatus() async {
    final projects = await listProjects();
    final statuses = <PostBaseProjectStatus>[];

    for (final project in projects) {
      final overview = await getProjectOverview(project.id);
      PostBaseCapabilityHealthReport? health;
      final primaryEnvironment = overview.environments.isNotEmpty
          ? overview.environments.first.environmentId
          : null;
      if (primaryEnvironment != null && primaryEnvironment.isNotEmpty) {
        health = await getCapabilityHealth(primaryEnvironment);
      }
      statuses.add(
        PostBaseProjectStatus(
          project: project,
          overview: overview,
          primaryEnvironmentHealth: health,
        ),
      );
    }

    return statuses;
  }
}
