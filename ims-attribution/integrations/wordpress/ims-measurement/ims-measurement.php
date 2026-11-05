<?php
/**
 * Plugin Name: IMS Measurement for WooCommerce
 * Description: Consent-gated IMS journey collection and checkout identity bridge. Verified revenue is read server-side through WooCommerce REST.
 * Version: 1.0.0
 */
defined('ABSPATH') || exit;
add_action('admin_menu', function(){add_options_page('IMS Measurement','IMS Measurement','manage_options','ims-measurement','ims_measurement_settings');});
add_action('admin_init',function(){
  register_setting('ims_measurement','ims_measurement_api',['sanitize_callback'=>'esc_url_raw']);
  register_setting('ims_measurement','ims_measurement_collect',['sanitize_callback'=>'esc_url_raw']);
  register_setting('ims_measurement','ims_measurement_tenant',['sanitize_callback'=>'sanitize_text_field']);
});
function ims_measurement_settings(){
  if(!current_user_can('manage_options'))return;
  echo '<div class="wrap"><h1>IMS Measurement</h1><p>Connect your CMP to the ims:consent browser event. Collection is denied by default. No advertising secrets belong in these fields.</p><form method="post" action="options.php">';
  settings_fields('ims_measurement');
  foreach(['api'=>'IMS API HTTPS origin','collect'=>'Server GTM collection HTTPS URL','tenant'=>'IMS tenant ID'] as $k=>$label){
    $name='ims_measurement_'.$k;
    echo '<p><label>'.esc_html($label).' <input class="regular-text" name="'.esc_attr($name).'" value="'.esc_attr(get_option($name,'')).'"></label></p>';
  }
  submit_button();echo '</form></div>';
}
add_action('wp_enqueue_scripts',function(){
  if(!function_exists('WC'))return;
  $api=get_option('ims_measurement_api','');$collect=get_option('ims_measurement_collect','');$tenant=get_option('ims_measurement_tenant','');
  if(strpos($api,'https://')!==0 || strpos($collect,'https://')!==0 || !$tenant)return;
  wp_enqueue_script('ims-measurement-sdk',plugins_url('pixel.js',__FILE__),[], '1.0.0',true);
  wp_enqueue_script('ims-measurement-bridge',plugins_url('bridge.js',__FILE__),['ims-measurement-sdk'],'1.0.0',true);
  wp_localize_script('ims-measurement-bridge','IMS_MERCHANT',['baseUrl'=>$api,'collectUrl'=>$collect,'tenant'=>$tenant,'ajax'=>admin_url('admin-ajax.php'),'nonce'=>wp_create_nonce('ims-measurement')]);
});
add_action('wp_ajax_ims_measurement_identity','ims_measurement_identity');
add_action('wp_ajax_nopriv_ims_measurement_identity','ims_measurement_identity');
function ims_measurement_identity(){
  check_ajax_referer('ims-measurement','nonce');
  if(!function_exists('WC') || !WC()->session)wp_send_json_error([],400);
  $id=sanitize_text_field(wp_unslash($_POST['visitor'] ?? ''));
  $allowed=($_POST['analytics'] ?? '')==='1';
  if(!$allowed){WC()->session->__unset('ims_visitor_id');wp_send_json_success();}
  if(!preg_match('/^[A-Za-z0-9_.:-]{1,160}$/',$id))wp_send_json_error([],400);
  WC()->session->set_customer_session_cookie(true);WC()->session->set('ims_visitor_id',$id);wp_send_json_success();
}
function ims_measurement_order_identity($order){
  if(!function_exists('WC') || !WC()->session)return;
  $id=WC()->session->get('ims_visitor_id');if($id)$order->update_meta_data('_ims_visitor_id',$id);
}
add_action('woocommerce_checkout_create_order','ims_measurement_order_identity');
add_action('woocommerce_store_api_checkout_update_order_meta','ims_measurement_order_identity');
