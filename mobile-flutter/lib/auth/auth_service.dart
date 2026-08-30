import 'dart:convert';

import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'session_store.dart';

/// Google sign-in -> n8n /webhook/auth/google -> session.
///
/// The app sends the RAW Google ID token from GoogleSignIn. The backend
/// verifies it server-side via the keyless tokeninfo endpoint. NOTE: do NOT
/// exchange it for a FirebaseAuth token — Firebase re-issued tokens are signed
/// with Firebase's own keys and tokeninfo rejects them (AUTH_INVALID_IDTOKEN).
/// The app only ever holds the returned HMAC session token, which becomes the
/// identity key for every later hook/register call (X-User-Token header).
class AuthService {
  AuthService._();
  static final AuthService instance = AuthService._();

  final GoogleSignIn _googleSignIn = GoogleSignIn();

  /// Performs the full Google sign-in and persists the session.
  /// Throws [StateError] with a stable code prefix (AUTH_*) on failure so the
  /// UI can surface a friendly message.
  Future<AuthSession> signInWithGoogle() async {
    final account = await _googleSignIn.signIn();
    if (account == null) {
      throw StateError('AUTH_CANCELLED');
    }
    final googleAuth = await account.authentication;
    final idToken = googleAuth.idToken;
    if (idToken == null) {
      throw StateError(
          'AUTH_NO_IDTOKEN: Google did not return an ID token '
          '(check the web client id / serverClientId config)');
    }

    final resp = await http
        .post(
          Uri.parse('$n8nBaseUrl/webhook/auth/google'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'idToken': idToken}),
        )
        .timeout(const Duration(seconds: 15));

    final Map<String, dynamic> body;
    try {
      body = jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      throw StateError('AUTH_SERVER: non-JSON response (${resp.statusCode})');
    }
    if (resp.statusCode != 200 || body['token'] == null) {
      throw StateError('AUTH_SERVER: ${body['error'] ?? resp.statusCode}');
    }

    final session = AuthSession.fromJson(body);
    await SessionStore.instance.save(session);
    return session;
  }

  Future<void> signOut() async {
    await _googleSignIn.signOut();
    await SessionStore.instance.clear();
  }
}
