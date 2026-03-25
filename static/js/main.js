/* ═══════════════════════════════════════════════════════
   Samba Fête — Main JavaScript
   ═══════════════════════════════════════════════════════ */

// ─── Sidebar Toggle (Mobile) ────────────────────────
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    if (sidebar) {
        sidebar.classList.toggle('open');
        if (overlay) {
            overlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
        }
    }
}

// ─── Swipe Gestures for Mobile ──────────────────────
(function() {
    let touchStartX = 0;
    let touchEndX = 0;
    
    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });
    
    document.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });
    
    function handleSwipe() {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;
        
        const diff = touchEndX - touchStartX;
        const threshold = 80;
        
        // Swipe right to open sidebar
        if (diff > threshold && touchStartX < 30) {
            sidebar.classList.add('open');
            document.querySelector('.sidebar-overlay')?.classList.add('active');
        }
        // Swipe left to close sidebar
        else if (diff < -threshold && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            document.querySelector('.sidebar-overlay')?.classList.remove('active');
        }
    }
})();

// ─── Auto-dismiss alerts ─────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // Format currency inputs
    const currencyInputs = document.querySelectorAll('input[name="total_amount"], input[name="deposit_required"], input[name="amount"], input[name^="line_amount"]');
    currencyInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            if (this.value) {
                this.value = Math.round(parseFloat(this.value) || 0);
            }
        });
    });

    // Form validation for deposit
    const depositInput = document.querySelector('input[name="deposit_required"]');
    if (depositInput) {
        depositInput.addEventListener('change', function() {
            if (parseFloat(this.value) < 20000) {
                this.value = 20000;
                showToast('L\'acompte minimum est de 20,000 DA', 'warning');
            }
        });
    }
});

// ─── Toast Notifications ─────────────────────────────
function showToast(message, type) {
    const container = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast-item toast-${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function createToastContainer() {
    const div = document.createElement('div');
    div.id = 'toast-container';
    div.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(div);
    return div;
}
