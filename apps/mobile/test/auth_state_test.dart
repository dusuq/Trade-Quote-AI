import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tradequote_mobile/core/storage/token_store.dart';
import 'package:tradequote_mobile/features/auth/domain/auth_state.dart';

class FakeTokenStore implements TokenStore {
  UserSession? saved;
  int saveCalls = 0;
  int clearCalls = 0;

  @override
  Future<void> save(UserSession session) async {
    saveCalls++;
    saved = session;
  }

  @override
  Future<UserSession?> load() async => saved;

  @override
  Future<void> clear() async {
    clearCalls++;
    saved = null;
  }
}

String _fakeJwt(Map<String, dynamic> claims) {
  String b64(Map<String, dynamic> m) =>
      base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
  return '${b64({
        'alg': 'none'
      })}.${b64(claims)}.sig';
}

void main() {
  group('AuthNotifier.login', () {
    test('decodes JWT claims into a UserSession and persists it', () async {
      final token = _fakeJwt({'sub': 'user-1', 'tid': 'tenant-1', 'roles': ['owner']});
      final client = MockClient((request) async {
        expect(request.url.path, '/v1/auth/login');
        return http.Response(
          jsonEncode({'access_token': token, 'refresh_token': 'refresh-1'}),
          200,
        );
      });
      final tokenStore = FakeTokenStore();
      final notifier = AuthNotifier(tokenStore: tokenStore, client: client);

      await notifier.login(
        slug: 'apex-trades',
        email: 'contractor@apex-trades.com',
        password: 'hunter2',
      );

      expect(notifier.state, isNotNull);
      expect(notifier.state!.userId, 'user-1');
      expect(notifier.state!.tenantId, 'tenant-1');
      expect(notifier.state!.role, 'owner');
      expect(notifier.state!.accessToken, token);

      expect(tokenStore.saveCalls, 1);
      expect(tokenStore.saved!.userId, 'user-1');
    });

    test('defaults role to contractor when the token has no roles claim',
        () async {
      final token = _fakeJwt({'sub': 'user-2', 'tid': 'tenant-1'});
      final client = MockClient((request) async => http.Response(
          jsonEncode({'access_token': token, 'refresh_token': 'r'}), 200));
      final notifier =
          AuthNotifier(tokenStore: FakeTokenStore(), client: client);

      await notifier.login(
          slug: 'apex-trades', email: 'a@b.com', password: 'x');

      expect(notifier.state!.role, 'contractor');
    });

    test('a non-200 response throws and never persists a session', () async {
      final client = MockClient((request) async =>
          http.Response(jsonEncode({'message': 'Invalid credentials'}), 401));
      final tokenStore = FakeTokenStore();
      final notifier = AuthNotifier(tokenStore: tokenStore, client: client);

      await expectLater(
        () => notifier.login(
            slug: 'apex-trades', email: 'bad@b.com', password: 'wrong'),
        throwsA(predicate(
            (e) => e is Exception && e.toString().contains('Invalid credentials'))),
      );

      expect(notifier.state, isNull);
      expect(tokenStore.saveCalls, 0);
    });
  });

  group('AuthNotifier.logout', () {
    test('clears in-memory state and the persisted session', () async {
      final tokenStore = FakeTokenStore();
      final token = _fakeJwt({'sub': 'u', 'tid': 't'});
      final client = MockClient((request) async => http.Response(
          jsonEncode({'access_token': token, 'refresh_token': 'r'}), 200));
      final notifier = AuthNotifier(tokenStore: tokenStore, client: client);
      await notifier.login(slug: 's', email: 'e@e.com', password: 'p');

      await notifier.logout();

      expect(notifier.state, isNull);
      expect(tokenStore.clearCalls, 1);
      expect(tokenStore.saved, isNull);
    });
  });

  group('AuthNotifier.restoreSession', () {
    test('rehydrates state from a previously persisted session', () async {
      final tokenStore = FakeTokenStore()
        ..saved = UserSession(
          userId: 'u1',
          tenantId: 't1',
          email: 'e@e.com',
          name: 'e',
          role: 'owner',
          tenantName: 'apex-trades',
          accessToken: 'atk',
          refreshToken: 'rtk',
        );
      final notifier = AuthNotifier(tokenStore: tokenStore);

      expect(notifier.state, isNull, reason: 'no restore has run yet');
      await notifier.restoreSession();

      expect(notifier.state, isNotNull);
      expect(notifier.state!.userId, 'u1');
      expect(notifier.state!.accessToken, 'atk');
    });

    test('leaves state null when nothing was persisted', () async {
      final notifier = AuthNotifier(tokenStore: FakeTokenStore());
      await notifier.restoreSession();
      expect(notifier.state, isNull);
    });
  });

  group('UserSession JSON round-trip', () {
    test('toJson/fromJson preserves every field', () {
      final session = UserSession(
        userId: 'u',
        tenantId: 't',
        email: 'e@e.com',
        name: 'E',
        role: 'owner',
        tenantName: 'apex',
        accessToken: 'a',
        refreshToken: 'r',
      );
      final roundTripped = UserSession.fromJson(session.toJson());
      expect(roundTripped.toJson(), session.toJson());
    });
  });
}
