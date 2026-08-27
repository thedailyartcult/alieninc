        console.log('[centra-login] v3 ready, supabase lib:', !!window.supabase);
        const SUPABASE_URL = 'https://frwjaixxlgthkgjtafhz.supabase.co';
        const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZyd2phaXh4bGd0aGtnanRhZmh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDUzNDQsImV4cCI6MjA5NDYyMTM0NH0.j2DKz__QMml4WplMYNmsQpTUw0qu-kZG7Md3qBEEdEc';
        const supabase = window.supabase ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;
        function auditCentraLogin(email, ok, code){ try{ fetch('/api/v1/auth/login-audit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email||'',success:!!ok,error_code:code||'',source:'centra'})}).catch(function(){});}catch(_){} }

        document.addEventListener('DOMContentLoaded', function() {
            const toggle = document.getElementById('togglePassword');
            const passwordField = document.getElementById('password');
            const loginForm = document.querySelector('.login-form');
            const loginBtn = document.querySelector('.btn-login');
            const emailInput = document.getElementById('email');

            // Toggle password visibility
            toggle.addEventListener('click', function() {
                const type = passwordField.getAttribute('type') === 'password' ? 'text' : 'password';
                passwordField.setAttribute('type', type);

                const svg = toggle.querySelector('svg');
                if (type === 'text') {
                    svg.innerHTML = `
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                    `;
                } else {
                    svg.innerHTML = `
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                    `;
                }
            });

            function resetBtn() {
                loginBtn.disabled = false;
                loginBtn.innerHTML = 'Log In <svg viewBox="0 0 8 12" xmlns="http://www.w3.org/2000/svg"><polygon points="0 1.4 1.4 0 7.4 6 1.4 12 0 10.6 4.6 6" fill="currentColor"></polygon></svg>';
            }

            // Handle login form submission
            loginForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                const email = emailInput.value.trim();
                const password = passwordField.value;

                if (!email || !password) {
                    alert('Please enter email and password');
                    return;
                }

                if (!supabase) {
                    alert('Login is unavailable — the auth library failed to load. Check your connection and reload.');
                    return;
                }

                loginBtn.disabled = true;
                loginBtn.textContent = 'Signing in...';

                try {
                    const { data, error } = await supabase.auth.signInWithPassword({
                        email: email,
                        password: password
                    });

                    if (error) {
                        auditCentraLogin(email, false, error.message||'auth_error');
                        alert('Authentication failed: ' + error.message);
                        resetBtn();
                        return;
                    }

                    // Store session in localStorage
                    const session = {
                        username: data.user.email,
                        user_id: data.user.id,
                        access_token: data.session.access_token,
                        refresh_token: data.session.refresh_token,
                        company_id: 'alieninc'
                    };
                    localStorage.setItem('hs_session', JSON.stringify(session));
                    auditCentraLogin(email, true, '');

                    // Redirect to dashboard
                    window.location.href = 'index.html';
                } catch (err) {
                    auditCentraLogin(email, false, err.message||'fetch_error');
                    alert('Login error: ' + err.message);
                    resetBtn();
                }
            });
        });
