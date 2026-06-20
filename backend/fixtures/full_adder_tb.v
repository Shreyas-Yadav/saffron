// Golden testbench: exhaustively drives the 3 inputs of full_adder and
// dumps a VCD so we can render a waveform.
`timescale 1ns/1ps
module full_adder_tb;
    reg  a, b, cin;
    wire sum, cout;

    full_adder dut (.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));

    integer i;
    initial begin
        $dumpfile("full_adder.vcd");
        $dumpvars(0, full_adder_tb);
        for (i = 0; i < 8; i = i + 1) begin
            {a, b, cin} = i[2:0];
            #10;
        end
        $finish;
    end
endmodule
