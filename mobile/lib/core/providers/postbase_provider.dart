import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/postbase_status.dart';
import '../repositories/postbase_repository.dart';
import 'dio_provider.dart';

final postBaseRepositoryProvider = Provider<PostBaseRepository>((ref) {
  return PostBaseRepository(ref.watch(dioClientProvider));
});

class PostBasePlatformStatusNotifier
    extends StateNotifier<AsyncValue<PostBasePlatformSnapshot>> {
  PostBasePlatformStatusNotifier(this._repository)
      : super(const AsyncValue.loading()) {
    load();
  }

  final PostBaseRepository _repository;
  List<PostBaseProjectStatus> _lastStatuses = const [];

  Future<void> load() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() async {
      final snapshot = await _repository.getPlatformStatusSnapshot(
        previousStatuses: _lastStatuses,
      );
      _lastStatuses = snapshot.statuses;
      return snapshot;
    });
  }
}

final postBasePlatformStatusProvider = StateNotifierProvider<
    PostBasePlatformStatusNotifier, AsyncValue<PostBasePlatformSnapshot>>(
  (ref) => PostBasePlatformStatusNotifier(ref.watch(postBaseRepositoryProvider)),
);
