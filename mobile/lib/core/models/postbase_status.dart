class PostBaseProjectRead {
  final String id;
  final String name;
  final String slug;
  final String description;
  final bool isActive;

  const PostBaseProjectRead({
    required this.id,
    required this.name,
    required this.slug,
    required this.description,
    required this.isActive,
  });

  factory PostBaseProjectRead.fromJson(Map<String, dynamic> json) {
    return PostBaseProjectRead(
      id: json['id'] as String,
      name: json['name'] as String? ?? '',
      slug: json['slug'] as String? ?? '',
      description: json['description'] as String? ?? '',
      isActive: json['is_active'] as bool? ?? false,
    );
  }
}

class PostBaseEnvironmentOverview {
  final String environmentId;
  final String stage;
  final String status;
  final String readinessState;
  final String readinessDetail;
  final int activeBindings;
  final int degradedBindings;
  final int recentSwitchovers;
  final int pendingMigrations;
  final int driftedMigrations;
  final int secretCount;
  final int keyCount;
  final double usagePointsTotal;
  final int recentAuditEvents;
  final String quotaState;
  final bool quotaWarningTriggered;
  final bool quotaSoftLimited;
  final bool quotaHardLimited;
  final double quotaUtilization;
  final String degradationMode;

  const PostBaseEnvironmentOverview({
    required this.environmentId,
    required this.stage,
    required this.status,
    required this.readinessState,
    required this.readinessDetail,
    required this.activeBindings,
    required this.degradedBindings,
    required this.recentSwitchovers,
    required this.pendingMigrations,
    required this.driftedMigrations,
    required this.secretCount,
    required this.keyCount,
    required this.usagePointsTotal,
    required this.recentAuditEvents,
    required this.quotaState,
    required this.quotaWarningTriggered,
    required this.quotaSoftLimited,
    required this.quotaHardLimited,
    required this.quotaUtilization,
    required this.degradationMode,
  });

  factory PostBaseEnvironmentOverview.fromJson(Map<String, dynamic> json) {
    return PostBaseEnvironmentOverview(
      environmentId: json['environment_id'] as String? ?? '',
      stage: json['stage'] as String? ?? 'development',
      status: json['status'] as String? ?? 'inactive',
      readinessState: json['readiness_state'] as String? ?? 'not_ready',
      readinessDetail: json['readiness_detail'] as String? ?? '',
      activeBindings: json['active_bindings'] as int? ?? 0,
      degradedBindings: json['degraded_bindings'] as int? ?? 0,
      recentSwitchovers: json['recent_switchovers'] as int? ?? 0,
      pendingMigrations: json['pending_migrations'] as int? ?? 0,
      driftedMigrations: json['drifted_migrations'] as int? ?? 0,
      secretCount: json['secret_count'] as int? ?? 0,
      keyCount: json['key_count'] as int? ?? 0,
      usagePointsTotal: (json['usage_points_total'] as num?)?.toDouble() ?? 0,
      recentAuditEvents: json['recent_audit_events'] as int? ?? 0,
      quotaState: json['quota_state'] as String? ?? 'healthy',
      quotaWarningTriggered: json['quota_warning_triggered'] as bool? ?? false,
      quotaSoftLimited: json['quota_soft_limited'] as bool? ?? false,
      quotaHardLimited: json['quota_hard_limited'] as bool? ?? false,
      quotaUtilization: (json['quota_utilization'] as num?)?.toDouble() ?? 0,
      degradationMode: json['degradation_mode'] as String? ?? 'none',
    );
  }
}

class PostBaseProjectOverview {
  final String projectId;
  final int environmentCount;
  final int activeEnvironmentCount;
  final int activeBindings;
  final int degradedBindings;
  final int secretCount;
  final double usagePointsTotal;
  final int recentAuditEvents;
  final List<PostBaseEnvironmentOverview> environments;

  const PostBaseProjectOverview({
    required this.projectId,
    required this.environmentCount,
    required this.activeEnvironmentCount,
    required this.activeBindings,
    required this.degradedBindings,
    required this.secretCount,
    required this.usagePointsTotal,
    required this.recentAuditEvents,
    required this.environments,
  });

  factory PostBaseProjectOverview.fromJson(Map<String, dynamic> json) {
    final environments = (json['environments'] as List<dynamic>? ?? const [])
        .map((item) =>
            PostBaseEnvironmentOverview.fromJson(item as Map<String, dynamic>))
        .toList();

    return PostBaseProjectOverview(
      projectId: json['project_id'] as String? ?? '',
      environmentCount: json['environment_count'] as int? ?? 0,
      activeEnvironmentCount: json['active_environment_count'] as int? ?? 0,
      activeBindings: json['active_bindings'] as int? ?? 0,
      degradedBindings: json['degraded_bindings'] as int? ?? 0,
      secretCount: json['secret_count'] as int? ?? 0,
      usagePointsTotal: (json['usage_points_total'] as num?)?.toDouble() ?? 0,
      recentAuditEvents: json['recent_audit_events'] as int? ?? 0,
      environments: environments,
    );
  }
}

class PostBaseProviderHealthRead {
  final String capabilityKey;
  final String providerKey;
  final bool ready;
  final String detail;

  const PostBaseProviderHealthRead({
    required this.capabilityKey,
    required this.providerKey,
    required this.ready,
    required this.detail,
  });

  factory PostBaseProviderHealthRead.fromJson(Map<String, dynamic> json) {
    return PostBaseProviderHealthRead(
      capabilityKey: json['capability_key'] as String? ?? '',
      providerKey: json['provider_key'] as String? ?? '',
      ready: json['ready'] as bool? ?? false,
      detail: json['detail'] as String? ?? '',
    );
  }
}

class PostBaseCapabilityHealthReport {
  final String environmentId;
  final bool overallReady;
  final List<String> degradedCapabilities;
  final List<PostBaseProviderHealthRead> providerHealth;

  const PostBaseCapabilityHealthReport({
    required this.environmentId,
    required this.overallReady,
    required this.degradedCapabilities,
    required this.providerHealth,
  });

  factory PostBaseCapabilityHealthReport.fromJson(Map<String, dynamic> json) {
    return PostBaseCapabilityHealthReport(
      environmentId: json['environment_id'] as String? ?? '',
      overallReady: json['overall_ready'] as bool? ?? false,
      degradedCapabilities: (json['degraded_capabilities'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      providerHealth: (json['provider_health'] as List<dynamic>? ?? const [])
          .map((item) => PostBaseProviderHealthRead.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PostBaseProjectStatus {
  final PostBaseProjectRead project;
  final PostBaseProjectOverview overview;
  final PostBaseCapabilityHealthReport? primaryEnvironmentHealth;
  final bool hasDegradedBackendState;
  final String? degradedReason;

  const PostBaseProjectStatus({
    required this.project,
    required this.overview,
    required this.primaryEnvironmentHealth,
    this.hasDegradedBackendState = false,
    this.degradedReason,
  });
}

class PostBasePlatformSnapshot {
  final List<PostBaseProjectStatus> statuses;
  final bool isFromCache;
  final bool isStale;
  final DateTime fetchedAt;
  final String? warning;

  const PostBasePlatformSnapshot({
    required this.statuses,
    required this.isFromCache,
    required this.isStale,
    required this.fetchedAt,
    this.warning,
  });
}
