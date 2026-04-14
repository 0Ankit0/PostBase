import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/models/paginated_response.dart';
import '../../../../core/providers/dio_provider.dart';
import '../../../auth/presentation/providers/auth_provider.dart';
import '../../data/models/tenant_invitation.dart';
import '../../data/repositories/tenant_invitation_repository.dart';

final tenantInvitationRepositoryProvider =
    Provider<TenantInvitationRepository>((ref) {
  return TenantInvitationRepository(ref.watch(dioClientProvider));
});

final tenantInvitationsProvider = FutureProvider.family<
    PaginatedResponse<TenantInvitation>, ({int skip, int limit, String? status})>(
  (ref, params) => ref.watch(tenantInvitationRepositoryProvider).getMyInvitations(
        skip: params.skip,
        limit: params.limit,
        status: params.status,
      ),
);

final pendingTenantInvitationsProvider =
    FutureProvider<List<TenantInvitation>>((ref) async {
  final authState = ref.watch(authNotifierProvider).valueOrNull;
  if (authState?.isAuthenticated != true) {
    return const <TenantInvitation>[];
  }
  final result = await ref
      .watch(tenantInvitationRepositoryProvider)
      .getMyInvitations(status: 'pending');
  return result.items;
});
