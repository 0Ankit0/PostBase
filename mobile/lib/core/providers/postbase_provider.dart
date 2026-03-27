import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/postbase_status.dart';
import '../repositories/postbase_repository.dart';
import 'dio_provider.dart';

final postBaseRepositoryProvider = Provider<PostBaseRepository>((ref) {
  return PostBaseRepository(ref.watch(dioClientProvider));
});

final postBasePlatformStatusProvider = FutureProvider<List<PostBaseProjectStatus>>((
  ref,
) async {
  return ref.watch(postBaseRepositoryProvider).getPlatformStatus();
});
