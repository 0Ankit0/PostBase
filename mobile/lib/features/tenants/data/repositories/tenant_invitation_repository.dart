import '../../../../core/error/error_handler.dart';
import '../../../../core/models/paginated_response.dart';
import '../../../../core/network/api_endpoints.dart';
import '../../../../core/network/dio_client.dart';
import '../models/tenant_invitation.dart';

class TenantInvitationRepository {
  final DioClient _dioClient;

  TenantInvitationRepository(this._dioClient);

  Future<PaginatedResponse<TenantInvitation>> getMyInvitations({
    int skip = 0,
    int limit = 20,
    String? status,
  }) async {
    try {
      final response = await _dioClient.dio.get(
        ApiEndpoints.myTenantInvitations,
        queryParameters: {
          'skip': skip,
          'limit': limit,
          if (status != null) 'status': status,
        },
      );
      return PaginatedResponse.fromJson(
        response.data as Map<String, dynamic>,
        TenantInvitation.fromJson,
      );
    } catch (e) {
      throw ErrorHandler.handle(e);
    }
  }

  Future<void> acceptInvitation(String token) async {
    try {
      await _dioClient.dio.post(
        ApiEndpoints.acceptTenantInvitation,
        data: {'token': token},
      );
    } catch (e) {
      throw ErrorHandler.handle(e);
    }
  }

  Future<void> declineInvitation(String token) async {
    try {
      await _dioClient.dio.post(
        ApiEndpoints.declineTenantInvitation,
        data: {'token': token},
      );
    } catch (e) {
      throw ErrorHandler.handle(e);
    }
  }
}
