// Follow this setup guide to integrate the Deno language server with your editor:
// https://deno.land/manual/getting_started/setup_your_environment
// This enables autocomplete, go to definition, etc.

// Setup type definitions for built-in Supabase Runtime APIs
/// <reference types="https://esm.sh/@supabase/functions-js/src/edge-runtime.d.ts" />
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async (req: Request) => {
  console.log("Received request");

  const authHeader = req.headers.get("Authorization")!;

  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 })
  }

  try {
    const json = await req.json();
    console.log(json);
    const {
      result,
      amount,
      store_id,
      our_ref,
      payment_method,
      customer_phone,
      custom_ref
    } = json;

    // Check if payment was successful
    if (result !== "success") {
      throw new Error('Payment not successful');
    }

    // Convert the amount from string to numeric
    const amountNumeric = parseFloat(amount);
    // Extract user_id from custom_ref
    const userId = custom_ref.split('-')[0];

    // Connect to your Supabase database

    const supabaseClient = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_ANON_KEY") ?? "",
    );
    console.log("this is the supabase client" + supabaseClient)

    const { data, error } = await supabaseClient
      .from('payments')
      .select('amount')
      .eq('user_id', userId);
    console.log("the balance is:"+ data )
    if (error) {
        throw new Error(`Failed to retrieve balance: ${data || 'No data found'}`);
    }

    // Ensure that a valid amount is available
    let userBalance = 0;
    if (data[0] && !isNaN(parseFloat(data[0].amount))) {
      userBalance = parseFloat(data[0].amount);
    }
    const toAdd = amountNumeric + userBalance;

    // Update the user balance. Assuming custom_ref is the user_id.
    const { updated, theError } = await supabaseClient
      .from('payments')
      .update({ amount: toAdd})
      .eq('user_id', userId);

    if (theError) {
      throw new Error(`Failed to update balance: ${theError.message}`);
    }

    return new Response(JSON.stringify({ status: 'success', message: 'Balance updated', data: updated }), {
      headers: { 'Content-Type': 'application/json' },
      status: 200
    });
  } catch (error) {
    return new Response(JSON.stringify({ status: 'error', message: error.message }), {
      headers: { 'Content-Type': 'application/json' },
      status: 500
    });
  }
}); // Closing parenthesis and brace for the Deno.serve() function

//  curl -i --location --request POST 'https://pzcrxgkcaiqyzdobwwgi.supabase.co/functions/v1/tlync-webhook' \
//     --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6Y3J4Z2tjYWlxeXpkb2J3d2dpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDk4MTU5MzMsImV4cCI6MjAyNTM5MTkzM30.1Yu71xxGpVYfIpmEZwB69jLHrstQf8ST6ybAAfAIhV8' \
//     --header 'Content-Type: application/json' \
//     --data '{
//             "result":"success",
//             "amount":"100.0",
//             "store_id":"xxxxxxx...",
//             "our_ref":"SSSSS",
//             "payment_method":"tadawul",
//             "customer_phone":"+218000000",
//             "custom_ref":"5841920454-68e35996-d379-4f99-b1a6-3da4252e657e"
//             }'
