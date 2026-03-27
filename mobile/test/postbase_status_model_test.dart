import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/models/postbase_status.dart';

void main() {
  test('PostBaseProjectOverview.fromJson parses environment readiness fields', () {
    final overview = PostBaseProjectOverview.fromJson({
      'project_id': 'proj_1',
      'environment_count': 1,
      'active_bindings': 4,
      'degraded_bindings': 1,
      'usage_points_total': 22.5,
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
          'usage_points_total': 12.25,
        },
      ],
    });

    expect(overview.projectId, 'proj_1');
    expect(overview.environments.first.readinessDetail, 'missing secret');
    expect(overview.environments.first.pendingMigrations, 1);
  });
}
