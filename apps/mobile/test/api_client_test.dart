import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tradequote_mobile/core/network/api_client.dart';

void main() {
  group('ApiClient headers', () {
    test('GET without a token omits Authorization', () async {
      http.Request? captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response('{"ok":true}', 200);
      });

      final api = ApiClient(baseUrl: 'http://gw.test', client: client);
      await api.get('/v1/customers');

      expect(captured!.headers['Authorization'], isNull);
      expect(captured!.headers['Content-Type'], 'application/json');
      expect(captured!.headers['Accept'], 'application/json');
      expect(captured!.url.toString(), 'http://gw.test/v1/customers');
    });

    test('requests carry Authorization: Bearer <token> when set', () async {
      http.Request? captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response('{}', 200);
      });

      final api =
          ApiClient(baseUrl: 'http://gw.test', token: 'tok123', client: client);
      await api.get('/v1/customers');

      expect(captured!.headers['Authorization'], 'Bearer tok123');
    });
  });

  group('ApiClient.get', () {
    test('returns decoded JSON on 200', () async {
      final client = MockClient((request) async {
        return http.Response(jsonEncode({'items': [1, 2, 3]}), 200);
      });
      final api = ApiClient(baseUrl: 'http://gw.test', client: client);

      final result = await api.get('/v1/customers');
      expect(result['items'], [1, 2, 3]);
    });

    test('returns null on empty 204 body', () async {
      final client = MockClient((request) async => http.Response('', 204));
      final api = ApiClient(baseUrl: 'http://gw.test', client: client);

      final result = await api.get('/v1/customers');
      expect(result, isNull);
    });

    test('throws on a 4xx response including status and body', () async {
      final client = MockClient(
          (request) async => http.Response('{"detail":"nope"}', 404));
      final api = ApiClient(baseUrl: 'http://gw.test', client: client);

      expect(
        () => api.get('/v1/customers/missing'),
        throwsA(
          predicate((e) =>
              e is Exception &&
              e.toString().contains('404') &&
              e.toString().contains('nope')),
        ),
      );
    });

    test('throws on a 5xx response', () async {
      final client =
          MockClient((request) async => http.Response('boom', 500));
      final api = ApiClient(baseUrl: 'http://gw.test', client: client);

      expect(() => api.get('/v1/customers'), throwsException);
    });

    test('wraps a network failure in an Exception', () async {
      final client = MockClient((request) async {
        throw const SocketExceptionStub('connection refused');
      });
      final api = ApiClient(baseUrl: 'http://gw.test', client: client);

      expect(
        () => api.get('/v1/customers'),
        throwsA(predicate((e) =>
            e is Exception && e.toString().contains('Network request failed'))),
      );
    });
  });

  group('ApiClient.post', () {
    test('sends the encoded JSON body and returns the decoded response',
        () async {
      http.Request? captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode({'id': 'abc'}), 201);
      });
      final api = ApiClient(baseUrl: 'http://gw.test', client: client);

      final result = await api.post('/v1/customers', {'name': 'Acme'});

      expect(jsonDecode(captured!.body), {'name': 'Acme'});
      expect(result['id'], 'abc');
    });
  });
}

/// Minimal stand-in for SocketException so this test file doesn't need
/// dart:io, which keeps it runnable on every test platform.
class SocketExceptionStub implements Exception {
  final String message;
  const SocketExceptionStub(this.message);
  @override
  String toString() => 'SocketExceptionStub: $message';
}
