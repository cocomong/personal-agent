import 'dart:async';

import 'package:flutter/material.dart';

import 'agent_screen.dart';
import 'auth/auth_service.dart';
import 'auth/login_screen.dart';
import 'auth/session_store.dart';
import 'notifications/fcm_service.dart';
import 'notifications/notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Show the UI immediately; all async setup (notifications, FCM, briefing
  // sync) runs in the background so a slow or hanging init can never leave a
  // blank launch screen. VapiClient.platformInitialized is awaited lazily by
  // VapiSessionController when a call actually starts.
  runApp(const PersonalAgentApp());
  unawaited(_bootstrap());
}

Future<void> _bootstrap() async {
  try {
    await NotificationService.instance.init();
    await FcmService.instance.init();
  } catch (e) {
    debugPrint('bootstrap error: $e');
  }
}

class PersonalAgentApp extends StatelessWidget {
  const PersonalAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Personal Agent',
      theme: ThemeData.dark(useMaterial3: true),
      home: const AuthGate(),
    );
  }
}

/// Restores the stored session and shows the agent screen when signed in,
/// otherwise the Google sign-in screen. The session token is the identity
/// key: every hook/register call carries it as X-User-Token so the backend
/// resolves the caller's company (doc/MULTITENANT.md).
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  AuthSession? _session;
  bool _restoring = true;

  @override
  void initState() {
    super.initState();
    SessionStore.instance.restore().then((s) {
      if (!mounted) return;
      setState(() {
        _session = s;
        _restoring = false;
      });
    });
  }

  void _onSignedIn(AuthSession session) {
    // Device was registered pre-login without identity; re-register so the
    // backend can associate the FCM token with this user/company.
    unawaited(FcmService.instance.registerAfterLogin());
    setState(() => _session = session);
  }

  Future<void> _onSignOut() async {
    await AuthService.instance.signOut();
    if (!mounted) return;
    setState(() => _session = null);
  }

  @override
  Widget build(BuildContext context) {
    if (_restoring) {
      return const Scaffold(
        backgroundColor: Color(0xFF0F172A),
        body: Center(
          child: CircularProgressIndicator(color: Color(0xFF2563EB)),
        ),
      );
    }
    final session = _session;
    if (session == null) {
      return LoginScreen(onSignedIn: _onSignedIn);
    }
    return AgentScreen(onSignOut: _onSignOut);
  }
}
