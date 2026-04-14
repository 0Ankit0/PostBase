enum TenantInvitationRole {
  owner,
  admin,
  member;

  static TenantInvitationRole fromString(String value) {
    switch (value) {
      case 'owner':
        return TenantInvitationRole.owner;
      case 'admin':
        return TenantInvitationRole.admin;
      default:
        return TenantInvitationRole.member;
    }
  }

  String get label => name;
}

enum TenantInvitationStatus {
  pending,
  accepted,
  declined,
  expired,
  revoked;

  static TenantInvitationStatus fromString(String value) {
    switch (value) {
      case 'accepted':
        return TenantInvitationStatus.accepted;
      case 'declined':
        return TenantInvitationStatus.declined;
      case 'expired':
        return TenantInvitationStatus.expired;
      case 'revoked':
        return TenantInvitationStatus.revoked;
      default:
        return TenantInvitationStatus.pending;
    }
  }
}

class TenantInvitation {
  final String id;
  final String tenantId;
  final String email;
  final TenantInvitationRole role;
  final TenantInvitationStatus status;
  final String token;
  final String tenantName;
  final String tenantSlug;
  final String tenantDescription;
  final bool tenantIsActive;
  final String expiresAt;
  final String createdAt;
  final String? acceptedAt;

  const TenantInvitation({
    required this.id,
    required this.tenantId,
    required this.email,
    required this.role,
    required this.status,
    required this.token,
    required this.tenantName,
    required this.tenantSlug,
    required this.tenantDescription,
    required this.tenantIsActive,
    required this.expiresAt,
    required this.createdAt,
    this.acceptedAt,
  });

  factory TenantInvitation.fromJson(Map<String, dynamic> json) {
    return TenantInvitation(
      id: json['id'].toString(),
      tenantId: json['tenant_id'].toString(),
      email: json['email'] as String? ?? '',
      role: TenantInvitationRole.fromString(json['role'] as String? ?? 'member'),
      status: TenantInvitationStatus.fromString(
        json['status'] as String? ?? 'pending',
      ),
      token: json['token'] as String? ?? '',
      tenantName: json['tenant_name'] as String? ?? '',
      tenantSlug: json['tenant_slug'] as String? ?? '',
      tenantDescription: json['tenant_description'] as String? ?? '',
      tenantIsActive: json['tenant_is_active'] as bool? ?? true,
      expiresAt: json['expires_at'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      acceptedAt: json['accepted_at'] as String?,
    );
  }
}
