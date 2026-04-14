import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/models/postbase_status.dart';

void main() {
  test('PostBaseProjectOverview.fromJson parses environment readiness fields', () {
    final overview = PostBaseProjectOverview.fromJson({
      'project_id': 'proj_1',
      'environment_count': 1,
      'active_environment_count': 1,
      'active_bindings': 4,
      'degraded_bindings': 1,
      'secret_count': 2,
      'usage_points_total': 22.5,
      'recent_audit_events': 9,
      'environments': [
        {
          'environment_id': 'env_1',
          'stage': 'staging',
          'status': 'degraded',
          'readiness_state': 'degraded',
          'readiness_detail': 'missing secret',
          'active_bindings': 3,
          'degraded_bindings': 1,
          'recent_switchovers': 2,
          'pending_migrations': 1,
          'drifted_migrations': 1,
          'secret_count': 2,
          'key_count': 1,
          'usage_points_total': 12.25,
          'recent_audit_events': 4,
          'quota_state': 'soft_limited',
          'quota_warning_triggered': true,
          'quota_soft_limited': true,
          'quota_hard_limited': false,
          'quota_utilization': 0.82,
          'degradation_mode': 'controlled',
        },
      ],
    });

    expect(overview.projectId, 'proj_1');
    expect(overview.activeEnvironmentCount, 1);
    expect(overview.recentAuditEvents, 9);
    expect(overview.environments.first.readinessDetail, 'missing secret');
    expect(overview.environments.first.pendingMigrations, 1);
    expect(overview.environments.first.quotaState, 'soft_limited');
    expect(overview.environments.first.quotaWarningTriggered, isTrue);
    expect(overview.environments.first.quotaUtilization, 0.82);
    expect(overview.environments.first.degradationMode, 'controlled');
  });
}
