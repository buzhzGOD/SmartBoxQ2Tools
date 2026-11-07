package local.smartboxq2.launcher

import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.Drawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.leanback.widget.HorizontalGridView
import androidx.recyclerview.widget.RecyclerView
import java.text.DateFormat
import java.util.Date
import java.util.Locale

private data class LaunchItem(
    val id: String,
    val label: String,
    val icon: Drawable?,
    val isSettings: Boolean = false,
)

class MainActivity : AppCompatActivity() {
    private val clockHandler = Handler(Looper.getMainLooper())
    private lateinit var clock: TextView
    private lateinit var favoritesRow: HorizontalGridView
    private lateinit var appsRow: HorizontalGridView
    private lateinit var favoritesAdapter: LaunchAdapter
    private lateinit var appsAdapter: LaunchAdapter
    private lateinit var favorites: FavoriteStore

    private val updateClock = object : Runnable {
        override fun run() {
            clock.text = DateFormat.getTimeInstance(DateFormat.SHORT, Locale.getDefault()).format(Date())
            clockHandler.postDelayed(this, 30_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        favorites = FavoriteStore(this)
        setContentView(createContent())
        refreshApps()
    }

    override fun onResume() {
        super.onResume()
        refreshApps()
        updateClock.run()
    }

    override fun onPause() {
        clockHandler.removeCallbacks(updateClock)
        super.onPause()
    }

    private fun createContent(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(ContextCompat.getColor(context, R.color.background))
            setPadding(dp(56), dp(34), dp(56), dp(34))
        }
        val header = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            orientation = LinearLayout.HORIZONTAL
        }
        val title = TextView(this).apply {
            text = getString(R.string.app_name)
            setTextColor(ContextCompat.getColor(context, R.color.text_primary))
            textSize = 28f
        }
        clock = TextView(this).apply {
            gravity = Gravity.END
            setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
            textSize = 24f
        }
        header.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        header.addView(clock, LinearLayout.LayoutParams(dp(190), ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(header)
        root.addView(sectionLabel("Избранное"), sectionParams(top = 38))
        favoritesRow = newRow().also { root.addView(it, rowParams()) }
        root.addView(sectionLabel("Все приложения"), sectionParams(top = 28))
        appsRow = newRow().also { root.addView(it, rowParams()) }
        root.addView(helpText(), sectionParams(top = 28))
        return root
    }

    private fun newRow(): HorizontalGridView = HorizontalGridView(this).apply {
        setNumRows(1)
        setRowHeight(dp(158))
        isFocusable = false
        itemAnimator = null
    }

    private fun sectionLabel(text: String) = TextView(this).apply {
        this.text = text
        textSize = 17f
        setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
    }

    private fun helpText() = TextView(this).apply {
        text = "OK — открыть · удерживать OK или Menu — добавить/убрать из избранного · Back — настройки"
        setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
        textSize = 14f
    }

    private fun sectionParams(top: Int) = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT,
    ).apply { topMargin = dp(top) }

    private fun rowParams() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        dp(166),
    ).apply { topMargin = dp(12) }

    private fun refreshApps() {
        val all = discoverApps()
        val favoriteIds = favorites.items()
        val favoriteItems = all.filter { it.id in favoriteIds }
        val settings = LaunchItem("__settings__", "Настройки Android", ContextCompat.getDrawable(this, R.drawable.ic_launcher), true)
        favoritesAdapter = LaunchAdapter(favoriteItems) { onItemAction(it) }
        appsAdapter = LaunchAdapter(listOf(settings) + all.filterNot { it.id in favoriteIds }) { onItemAction(it) }
        favoritesRow.adapter = favoritesAdapter
        appsRow.adapter = appsAdapter
        val first = favoriteItems.firstOrNull() ?: settings
        (if (favoriteItems.isNotEmpty()) favoritesRow else appsRow).post { requestInitialFocus(first) }
    }

    private fun requestInitialFocus(item: LaunchItem) {
        val row = if (item.id in favorites.items()) favoritesRow else appsRow
        row.findViewHolderForAdapterPosition(0)?.itemView?.requestFocus()
    }

    private fun discoverApps(): List<LaunchItem> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER)
        val fallbackIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val resolved = (packageManager.queryIntentActivities(intent, 0) + packageManager.queryIntentActivities(fallbackIntent, 0))
            .associateBy { it.activityInfo.packageName }
            .values
        return resolved.asSequence()
            .filter { it.activityInfo.packageName != packageName }
            .mapNotNull { info ->
                val packageId = info.activityInfo.packageName
                if (packageManager.getLaunchIntentForPackage(packageId) == null) null else LaunchItem(
                    packageId,
                    info.loadLabel(packageManager).toString(),
                    info.loadIcon(packageManager),
                )
            }
            .sortedBy { it.label.lowercase(Locale.getDefault()) }
            .toList()
    }

    private fun onItemAction(item: LaunchItem) {
        if (item.isSettings) {
            openSystemSettings()
            return
        }
        val intent = packageManager.getLaunchIntentForPackage(item.id)
        if (intent == null) {
            Toast.makeText(this, "Приложение больше недоступно", Toast.LENGTH_SHORT).show()
            refreshApps()
            return
        }
        try {
            startActivity(intent)
        } catch (_: Exception) {
            Toast.makeText(this, "Не удалось открыть ${item.label}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun toggleFavorite(item: LaunchItem) {
        if (!item.isSettings) {
            val added = favorites.toggle(item.id)
            Toast.makeText(this, if (added) "Добавлено в избранное" else "Убрано из избранного", Toast.LENGTH_SHORT).show()
            refreshApps()
        }
    }

    override fun onBackPressed() {
        showLauncherMenu()
    }

    private fun showLauncherMenu() {
        AlertDialog.Builder(this)
            .setTitle("Q2 Home")
            .setItems(arrayOf("Использовать как Home", "Открыть настройки Android", "Сбросить избранное", "Перезагрузить приставку")) { _, which ->
                when (which) {
                    0 -> requestHomeRole()
                    1 -> openSystemSettings()
                    2 -> { favorites.clear(); refreshApps() }
                    3 -> confirmReboot()
                }
            }
            .show()
    }

    private fun confirmReboot() {
        AlertDialog.Builder(this)
            .setTitle("Перезагрузка приставки")
            .setMessage("Полная перезагрузка завершает запущенные приложения и сбрасывает их состояние в оперативной памяти. На этой прошивке Q2 Home не имеет системного права запустить её сам: удерживайте Power на пульте и выберите «Перезагрузка», если этот пункт доступен.")
            .setNegativeButton("Отмена", null)
            .setPositiveButton("Настройки") { _, _ -> openSystemSettings() }
            .show()
    }

    private fun requestHomeRole() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                val roleManagerClass = Class.forName("android.app.role.RoleManager")
                val manager = getSystemService("role") ?: return openHomeSettings()
                val isAvailable = roleManagerClass.getMethod("isRoleAvailable", String::class.java)
                    .invoke(manager, "android.app.role.HOME") as? Boolean
                if (isAvailable == true) {
                    val requestIntent = roleManagerClass.getMethod("createRequestRoleIntent", String::class.java)
                        .invoke(manager, "android.app.role.HOME") as? Intent
                    if (requestIntent != null) {
                        startActivityForResult(requestIntent, REQUEST_HOME_ROLE)
                        return
                    }
                }
            } catch (_: ReflectiveOperationException) {
                // Fall through to the platform Home settings below.
            }
        }
        openHomeSettings()
    }

    private fun openHomeSettings() {
        try {
            startActivity(Intent(Settings.ACTION_HOME_SETTINGS))
        } catch (_: Exception) {
            Toast.makeText(this, "На этой прошивке выберите Home вручную в настройках Android", Toast.LENGTH_LONG).show()
        }
    }

    private fun openSystemSettings() {
        try {
            startActivity(Intent(Settings.ACTION_SETTINGS))
        } catch (_: Exception) {
            Toast.makeText(this, "Настройки Android недоступны", Toast.LENGTH_SHORT).show()
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private inner class LaunchAdapter(
        private val items: List<LaunchItem>,
        private val onClick: (LaunchItem) -> Unit,
    ) : RecyclerView.Adapter<LaunchHolder>() {
        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): LaunchHolder {
            val tile = LinearLayout(parent.context).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setBackgroundResource(R.drawable.tile_background)
                isFocusable = true
                isFocusableInTouchMode = true
                setPadding(dp(16), dp(14), dp(16), dp(12))
                minimumWidth = dp(190)
                minimumHeight = dp(150)
            }
            val icon = ImageView(parent.context).apply { layoutParams = LinearLayout.LayoutParams(dp(68), dp(68)) }
            val label = TextView(parent.context).apply {
                gravity = Gravity.CENTER
                maxLines = 2
                textSize = 15f
                setTextColor(ContextCompat.getColor(context, R.color.text_primary))
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) }
            }
            tile.addView(icon)
            tile.addView(label)
            return LaunchHolder(tile, icon, label)
        }

        override fun onBindViewHolder(holder: LaunchHolder, position: Int) {
            val item = items[position]
            holder.icon.setImageDrawable(item.icon)
            holder.label.text = item.label
            holder.itemView.setOnClickListener { onClick(item) }
            holder.itemView.setOnLongClickListener { toggleFavorite(item); true }
            holder.itemView.setOnKeyListener { _, keyCode, event ->
                if (event.action == KeyEvent.ACTION_UP && keyCode == KeyEvent.KEYCODE_MENU) {
                    toggleFavorite(item)
                    true
                } else false
            }
            holder.itemView.setOnFocusChangeListener { view, focused ->
                view.animate().scaleX(if (focused) 1.07f else 1f).scaleY(if (focused) 1.07f else 1f).setDuration(120).start()
                view.setBackgroundColor(if (focused) ContextCompat.getColor(this@MainActivity, R.color.focus) else Color.TRANSPARENT)
                if (!focused) view.setBackgroundResource(R.drawable.tile_background)
            }
        }

        override fun getItemCount() = items.size
    }

    private class LaunchHolder(view: View, val icon: ImageView, val label: TextView) : RecyclerView.ViewHolder(view)

    private class FavoriteStore(context: Context) {
        private val preferences: SharedPreferences = context.getSharedPreferences("launcher", Context.MODE_PRIVATE)
        fun items(): LinkedHashSet<String> = preferences.getString("favorites", "")
            .orEmpty().split('\n').filter { it.isNotBlank() }.toCollection(LinkedHashSet())
        fun toggle(packageName: String): Boolean {
            val values = items()
            val added = values.add(packageName)
            if (!added) values.remove(packageName)
            preferences.edit().putString("favorites", values.joinToString("\n")).apply()
            return added
        }
        fun clear() = preferences.edit().remove("favorites").apply()
    }

    private companion object {
        const val REQUEST_HOME_ROLE = 41
    }
}
