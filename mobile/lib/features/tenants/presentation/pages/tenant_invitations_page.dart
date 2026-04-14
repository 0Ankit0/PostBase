import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/analytics/analytics_events.dart';
import '../../../../core/analytics/analytics_provider.dart';
import '../../../../core/error/error_handler.dart';
import '../../data/models/tenant_invitation.dart';
import '../providers/tenant_invitation_provider.dart';

class TenantInvitationsPage extends ConsumerStatefulWidget {
  const TenantInvitationsPage({super.key});

  @override
  ConsumerState<TenantInvitationsPage> createState() =>
      _TenantInvitationsPageState();
}

class _TenantInvitationsPageState extends ConsumerState<TenantInvitationsPage> {
  String? _activeToken;
  String? _activeAction;

  Future<void> _handleDecision(
    TenantInvitation invitation,
    String action,
  ) async {
    setState(() {
      _activeToken = invitation.token;
      _activeAction = action;
    });

    try {
      final repository = ref.read(tenantInvitationRepositoryProvider);
      if (action == 'accept') {
        await repository.acceptInvitation(invitation.token);
        ref
            .read(analyticsServiceProvider)
            .capture(TenantAnalyticsEvents.memberJoined);
      } else {
        await repository.declineInvitation(invitation.token);
        ref
            .read(analyticsServiceProvider)
            .capture(TenantAnalyticsEvents.invitationDeclined);
      }
      ref.invalidate(pendingTenantInvitationsProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            action == 'accept'
                ? 'Invitation accepted.'
                : 'Invitation declined.',
          ),
          backgroundColor: Colors.green,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ErrorHandler.handle(e).message),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _activeToken = null;
          _activeAction = null;
        });
      }
    }
  }

  Future<void> _refresh() async {
    ref.invalidate(pendingTenantInvitationsProvider);
    await ref.read(pendingTenantInvitationsProvider.future);
  }

  @override
  Widget build(BuildContext context) {
    final invitationsAsync = ref.watch(pendingTenantInvitationsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Pending Invitations')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: invitationsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (err, _) => ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              const SizedBox(height: 120),
              Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    children: [
                      const Icon(Icons.error_outline,
                          size: 48, color: Colors.red),
                      const SizedBox(height: 12),
                      Text(
                        ErrorHandler.handle(err).message,
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: () => ref.invalidate(
                          pendingTenantInvitationsProvider,
                        ),
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          data: (invitations) {
            if (invitations.isEmpty) {
              return ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 120),
                  Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: 24),
                      child: Column(
                        children: [
                          Icon(Icons.mail_outline,
                              size: 48, color: Colors.grey),
                          SizedBox(height: 12),
                          Text(
                            'You have no pending organization invitations.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: Colors.grey),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              );
            }

            return ListView.builder(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              itemCount: invitations.length,
              itemBuilder: (context, index) {
                final invitation = invitations[index];
                final accepting = _activeToken == invitation.token &&
                    _activeAction == 'accept';
                final declining = _activeToken == invitation.token &&
                    _activeAction == 'decline';

                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          invitation.tenantName,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          invitation.tenantSlug,
                          style: const TextStyle(color: Colors.grey),
                        ),
                        if (invitation.tenantDescription.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text(
                            invitation.tenantDescription,
                            style: const TextStyle(fontSize: 13),
                          ),
                        ],
                        const SizedBox(height: 12),
                        Text(
                          'Role: ${invitation.role.label} · Expires ${_formatDate(invitation.expiresAt)}',
                          style: const TextStyle(color: Colors.grey),
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(
                              child: ElevatedButton(
                                onPressed: declining
                                    ? null
                                    : () => _handleDecision(
                                          invitation,
                                          'accept',
                                        ),
                                child: accepting
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.white,
                                        ),
                                      )
                                    : const Text('Accept'),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: OutlinedButton(
                                onPressed: accepting
                                    ? null
                                    : () => _handleDecision(
                                          invitation,
                                          'decline',
                                        ),
                                child: declining
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Text('Decline'),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  String _formatDate(String dateStr) {
    try {
      final dt = DateTime.parse(dateStr).toLocal();
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
    } catch (_) {
      return dateStr;
    }
  }
}
