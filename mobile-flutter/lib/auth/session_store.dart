import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Authenticated session (HMAC token + user summary) as returned by the
/// n8n /webhook/auth/google endpoint (doc/MULTITENANT.md section 4.1).
class AuthSession {
  final String token;
  final String userId;
  final String? name;
  final String? email;
  final int? companyId;
  final bool setupComplete;

  AuthSession({
    required this.token,
    required this.userId,
    this.name,
    this.email,
    this.companyId,
    required this.setupComplete,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    final user = (json['user'] as Map<String, dynamic>?) ?? const {};
    return AuthSession(
      token: json['token'] as String,
      userId: user['id'] as String? ?? '',
      name: user['name'] as String?,
      email: user['email'] as String?,
      companyId: user['company_id'] as int?,
      setupComplete: user['setup_complete'] == true,
    );
  }

  Map<String, dynamic> toJson() => {
        'token': token,
        'user': {
          'id': userId,
          'name': name,
          'email': email,
          'company_id': companyId,
          'setup_complete': setupComplete,
        },
      };
}

/// Secure local persistence for the session (flutter_secure_storage).
/// The token is sent as the `X-User-Token` header on hook/register calls so
/// the backend can resolve the caller's company (identity -> company).
class SessionStore {
  SessionStore._();
  static final SessionStore instance = SessionStore._();

  static const FlutterSecureStorage _storage = FlutterSecureStorage();
  static const String _key = 'auth_session';

  AuthSession? _session;

  AuthSession? get session => _session;
  String? get token => _session?.token;

  Future<AuthSession?> restore() async {
    if (_session != null) return _session;
    try {
      final raw = await _storage.read(key: _key);
      if (raw == null || raw.isEmpty) return null;
      _session = AuthSession.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      _session = null; // corrupt/legacy entry -> treat as signed out
    }
    return _session;
  }

  Future<void> save(AuthSession session) async {
    _session = session;
    await _storage.write(key: _key, value: jsonEncode(session.toJson()));
  }

  Future<void> clear() async {
    _session = null;
    await _storage.delete(key: _key);
  }
}
